"""
seeds/seed.py — Idempotent seed script for AdaptIQ.

Run: python seeds/seed.py

Creates:
- 15+ concepts (8 geography, 7 history)
- 30+ questions with IRT params
- 6 test users with realistic response histories
"""
import asyncio
import uuid
import json
import logging
import random
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    User, Concept, QuestionBank, QuestionConcept,
    UserConceptTheta, UserResponse, ChallengeRank, UserChallengeRank,
    ClassicSession
)
from dependencies import get_async_session_context
from auth.core.security import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def ensure_schema(db: AsyncSession) -> None:
    """Add missing columns to existing tables and create missing tables."""
    logger.info("Checking schema and adding missing columns/tables...")
    
    # Create engine for table creation
    from sqlalchemy.ext.asyncio import create_async_engine
    from config import DATABASE_URL
    from database.models import Base
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    # This will create any missing tables without touching existing ones
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created/verified")
    
    await engine.dispose()
    
    # Add missing columns with raw SQL (idempotent with IF NOT EXISTS workaround)
    # This handles columns that were added to models after tables were created
    alter_statements = [
        # ========== question_bank columns ==========
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='question_bank' AND column_name='hint') THEN
                ALTER TABLE question_bank ADD COLUMN hint TEXT;
            END IF;
        END $$;
        """,
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='question_bank' AND column_name='times_seen') THEN
                ALTER TABLE question_bank ADD COLUMN times_seen INTEGER DEFAULT 0 NOT NULL;
            END IF;
        END $$;
        """,
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='question_bank' AND column_name='primary_concept_id') THEN
                ALTER TABLE question_bank ADD COLUMN primary_concept_id UUID;
            END IF;
        END $$;
        """,
        # ========== users columns ==========
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='elo_global') THEN
                ALTER TABLE users ADD COLUMN elo_global FLOAT DEFAULT 0.0 NOT NULL;
            END IF;
        END $$;
        """,
        # ========== user_concept_theta columns ==========
        # Fix column name mismatch: responses_count -> response_count
        """
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='responses_count') THEN
                ALTER TABLE user_concept_theta RENAME COLUMN responses_count TO response_count;
            END IF;
        END $$;
        """,
        # Add response_count if it doesn't exist at all
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='response_count') THEN
                ALTER TABLE user_concept_theta ADD COLUMN response_count INTEGER DEFAULT 0 NOT NULL;
            END IF;
        END $$;
        """,
        # Add theta_variance if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='theta_variance') THEN
                ALTER TABLE user_concept_theta ADD COLUMN theta_variance FLOAT DEFAULT 1.0 NOT NULL;
            END IF;
        END $$;
        """,
        # Add last_updated if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='last_updated') THEN
                ALTER TABLE user_concept_theta ADD COLUMN last_updated TIMESTAMP DEFAULT NOW() NOT NULL;
            END IF;
        END $$;
        """,
        # Add created_at if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='created_at') THEN
                ALTER TABLE user_concept_theta ADD COLUMN created_at TIMESTAMP DEFAULT NOW() NOT NULL;
            END IF;
        END $$;
        """,
        # Add first_seen_at if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='first_seen_at') THEN
                ALTER TABLE user_concept_theta ADD COLUMN first_seen_at TIMESTAMP;
            END IF;
        END $$;
        """,
        # Add exposure_count if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='exposure_count') THEN
                ALTER TABLE user_concept_theta ADD COLUMN exposure_count INTEGER DEFAULT 0 NOT NULL;
            END IF;
        END $$;
        """,
        # ========== MISSING COLUMNS FROM MODEL (lines 130-133) ==========
        # Add mastery_level if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='mastery_level') THEN
                ALTER TABLE user_concept_theta ADD COLUMN mastery_level VARCHAR(20) DEFAULT 'BEGINNER' NOT NULL;
            END IF;
        END $$;
        """,
        # Add last_played_at if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='last_played_at') THEN
                ALTER TABLE user_concept_theta ADD COLUMN last_played_at TIMESTAMP DEFAULT NOW() NOT NULL;
            END IF;
        END $$;
        """,
        # Add updated_at if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='updated_at') THEN
                ALTER TABLE user_concept_theta ADD COLUMN updated_at TIMESTAMP DEFAULT NOW() NOT NULL;
            END IF;
        END $$;
        """,
        # Add concept_state if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_concept_theta' AND column_name='concept_state') THEN
                ALTER TABLE user_concept_theta ADD COLUMN concept_state VARCHAR(20) DEFAULT 'EXPLORING' NOT NULL;
            END IF;
        END $$;
        """,
    ]
    
    for stmt in alter_statements:
        try:
            await db.execute(text(stmt))
        except Exception as e:
            logger.warning(f"Schema update warning (may be ok): {e}")
    
    await db.commit()
    logger.info("Schema check complete")


# ────────────────────────────────────────────────────────────────────────────
# CONCEPTS
# ────────────────────────────────────────────────────────────────────────────
GEOGRAPHY_CONCEPTS = [
    {"name": "Amazon River Basin", "description": "The world's largest river drainage system in South America"},
    {"name": "Sahara Desert", "description": "The largest hot desert in the world, covering northern Africa"},
    {"name": "Himalayan Range", "description": "The highest mountain range on Earth, home to Mount Everest"},
    {"name": "Mediterranean Sea", "description": "Sea connected to the Atlantic, surrounded by Europe, Africa, and Asia"},
    {"name": "Great Barrier Reef", "description": "World's largest coral reef system off the coast of Australia"},
    {"name": "Arctic Circle", "description": "The polar region around Earth's North Pole"},
    {"name": "Nile River Delta", "description": "The delta formed by the Nile River in northern Egypt"},
    {"name": "Siberian Tundra", "description": "Vast treeless plain in northern Russia"},
]

HISTORY_CONCEPTS = [
    {"name": "Egyptian Empire", "description": "Ancient civilization along the Nile, known for pyramids and pharaohs"},
    {"name": "Roman Empire", "description": "Ancient empire centered on Rome, dominated Mediterranean for centuries"},
    {"name": "Mongol Empire", "description": "Largest contiguous land empire in history, founded by Genghis Khan"},
    {"name": "Ottoman Empire", "description": "Turkish empire that controlled much of Southeast Europe and Middle East"},
    {"name": "Byzantine Empire", "description": "Eastern continuation of the Roman Empire based in Constantinople"},
    {"name": "Greek City-States", "description": "Independent political entities of ancient Greece like Athens and Sparta"},
    {"name": "Persian Empire", "description": "Ancient empire founded by Cyrus the Great, known for tolerance"},
]


# ────────────────────────────────────────────────────────────────────────────
# QUESTIONS
# ────────────────────────────────────────────────────────────────────────────
QUESTIONS = [
    # GEOGRAPHY - Easy (β ≈ -2.0 to -1.0)
    {
        "text": "Which river is the longest in Africa?",
        "options": ["Nile", "Congo", "Niger", "Zambezi"],
        "correct_index": 0,
        "explanation": "The Nile River is the longest river in Africa at approximately 6,650 km, flowing through 11 countries.",
        "hint": "This river passes through Egypt and has a famous delta.",
        "beta": -2.0,
        "topic": "geography",
        "concept": "Nile River Delta"
    },
    {
        "text": "What is the largest desert in the world by area?",
        "options": ["Sahara", "Antarctic", "Arctic", "Gobi"],
        "correct_index": 1,
        "explanation": "The Antarctic Desert is the largest at 14.2 million km². The Sahara is the largest hot desert.",
        "hint": "Think about cold deserts - they exist at the poles.",
        "beta": -1.5,
        "topic": "geography",
        "concept": "Sahara Desert"
    },
    {
        "text": "On which continent is the Amazon River Basin located?",
        "options": ["South America", "Africa", "Asia", "Australia"],
        "correct_index": 0,
        "explanation": "The Amazon Basin is in South America, primarily in Brazil, covering about 7 million km².",
        "hint": "This continent is home to Brazil and the Amazon rainforest.",
        "beta": -2.0,
        "topic": "geography",
        "concept": "Amazon River Basin"
    },
    # GEOGRAPHY - Medium (β ≈ -0.5 to 0.5)
    {
        "text": "Which mountain in the Himalayas is the highest peak on Earth?",
        "options": ["Mount Everest", "K2", "Kangchenjunga", "Lhotse"],
        "correct_index": 0,
        "explanation": "Mount Everest at 8,849 meters is the highest peak on Earth, located on the Nepal-Tibet border.",
        "hint": "This peak was named after a British surveyor.",
        "beta": -0.5,
        "topic": "geography",
        "concept": "Himalayan Range"
    },
    {
        "text": "The Great Barrier Reef is located off the coast of which country?",
        "options": ["Australia", "Indonesia", "Philippines", "Japan"],
        "correct_index": 0,
        "explanation": "The Great Barrier Reef stretches over 2,300 km along Australia's northeast coast in the Coral Sea.",
        "hint": "This country is both a continent and a nation.",
        "beta": 0.0,
        "topic": "geography",
        "concept": "Great Barrier Reef"
    },
    {
        "text": "Which sea is bordered by Europe, Africa, and Asia?",
        "options": ["Mediterranean Sea", "Black Sea", "Red Sea", "Caspian Sea"],
        "correct_index": 0,
        "explanation": "The Mediterranean Sea is almost completely enclosed by land from three continents.",
        "hint": "Its name comes from Latin meaning 'middle of the land'.",
        "beta": 0.0,
        "topic": "geography",
        "concept": "Mediterranean Sea"
    },
    # GEOGRAPHY - Hard (β ≈ 1.0 to 2.0)
    {
        "text": "What percentage of Russia's territory does Siberia approximately cover?",
        "options": ["77%", "50%", "65%", "90%"],
        "correct_index": 0,
        "explanation": "Siberia covers about 77% of Russia's total area, extending from the Ural Mountains to the Pacific.",
        "hint": "It's more than half but less than 80%.",
        "beta": 1.5,
        "topic": "geography",
        "concept": "Siberian Tundra"
    },
    {
        "text": "At what latitude does the Arctic Circle begin?",
        "options": ["66°33' N", "60° N", "70° N", "63° N"],
        "correct_index": 0,
        "explanation": "The Arctic Circle is at approximately 66°33'47\" N, marking where the midnight sun occurs.",
        "hint": "It's about two-thirds of the way from the equator to the pole.",
        "beta": 2.0,
        "topic": "geography",
        "concept": "Arctic Circle"
    },
    {
        "text": "How many countries does the Amazon River flow through?",
        "options": ["9", "5", "7", "11"],
        "correct_index": 0,
        "explanation": "The Amazon flows through Peru, Colombia, and Brazil, while its basin touches 9 countries total.",
        "hint": "The number is single digits but more than most people guess.",
        "beta": 1.0,
        "topic": "geography",
        "concept": "Amazon River Basin"
    },
    # HISTORY - Easy (β ≈ -2.0 to -1.0)
    {
        "text": "Who founded the Mongol Empire?",
        "options": ["Genghis Khan", "Kublai Khan", "Tamerlane", "Attila"],
        "correct_index": 0,
        "explanation": "Genghis Khan united the Mongol tribes in 1206 and founded the Mongol Empire.",
        "hint": "His name means 'universal ruler'.",
        "beta": -2.0,
        "topic": "history",
        "concept": "Mongol Empire"
    },
    {
        "text": "What ancient structure was built as a tomb for the Egyptian pharaohs?",
        "options": ["Pyramids", "Colosseum", "Parthenon", "Stonehenge"],
        "correct_index": 0,
        "explanation": "The Egyptian pyramids, particularly at Giza, were built as elaborate tombs for pharaohs.",
        "hint": "These structures have a triangular shape.",
        "beta": -2.0,
        "topic": "history",
        "concept": "Egyptian Empire"
    },
    {
        "text": "What was the capital of the Byzantine Empire?",
        "options": ["Constantinople", "Rome", "Athens", "Alexandria"],
        "correct_index": 0,
        "explanation": "Constantinople (modern Istanbul) was the capital of the Byzantine Empire from 330 CE.",
        "hint": "This city straddles Europe and Asia.",
        "beta": -1.5,
        "topic": "history",
        "concept": "Byzantine Empire"
    },
    # HISTORY - Medium (β ≈ -0.5 to 0.5)
    {
        "text": "Which city-state was known for its powerful navy in ancient Greece?",
        "options": ["Athens", "Sparta", "Thebes", "Corinth"],
        "correct_index": 0,
        "explanation": "Athens developed a powerful navy and dominated the Delian League, a naval alliance.",
        "hint": "This city was also the birthplace of democracy.",
        "beta": 0.0,
        "topic": "history",
        "concept": "Greek City-States"
    },
    {
        "text": "What was the official language of the Roman Empire?",
        "options": ["Latin", "Greek", "Aramaic", "Etruscan"],
        "correct_index": 0,
        "explanation": "Latin was the official language of the Roman Empire and Roman law.",
        "hint": "This language is the ancestor of Romance languages like Spanish and French.",
        "beta": -0.5,
        "topic": "history",
        "concept": "Roman Empire"
    },
    {
        "text": "Who was the founder of the Persian Empire?",
        "options": ["Cyrus the Great", "Darius I", "Xerxes", "Artaxerxes"],
        "correct_index": 0,
        "explanation": "Cyrus the Great founded the Achaemenid Persian Empire around 550 BCE.",
        "hint": "He was known for his respect for the customs of conquered peoples.",
        "beta": 0.0,
        "topic": "history",
        "concept": "Persian Empire"
    },
    # HISTORY - Hard (β ≈ 1.0 to 2.0)
    {
        "text": "In what year did Constantinople fall to the Ottoman Empire?",
        "options": ["1453", "1492", "1389", "1517"],
        "correct_index": 0,
        "explanation": "Constantinople fell to Sultan Mehmed II on May 29, 1453, ending the Byzantine Empire.",
        "hint": "This event happened about 40 years before Columbus reached the Americas.",
        "beta": 1.0,
        "topic": "history",
        "concept": "Ottoman Empire"
    },
    {
        "text": "What was the extent of the Mongol Empire at its peak?",
        "options": ["24 million km²", "12 million km²", "18 million km²", "30 million km²"],
        "correct_index": 0,
        "explanation": "The Mongol Empire covered about 24 million km² at its peak, the largest contiguous land empire ever.",
        "hint": "It was larger than the Roman Empire but smaller than the British Empire.",
        "beta": 1.5,
        "topic": "history",
        "concept": "Mongol Empire"
    },
    {
        "text": "Which pharaoh is credited with building the Great Pyramid of Giza?",
        "options": ["Khufu", "Ramesses II", "Tutankhamun", "Cleopatra"],
        "correct_index": 0,
        "explanation": "Pharaoh Khufu (also known as Cheops) built the Great Pyramid around 2560 BCE.",
        "hint": "His Greek name starts with 'Ch'.",
        "beta": 1.0,
        "topic": "history",
        "concept": "Egyptian Empire"
    },
    {
        "text": "How long did the Roman Empire last (including Eastern Roman)?",
        "options": ["About 1,500 years", "About 500 years", "About 1,000 years", "About 2,000 years"],
        "correct_index": 0,
        "explanation": "From 27 BCE to 1453 CE (fall of Constantinople), the Roman/Byzantine Empire lasted ~1,500 years.",
        "hint": "If you count the Eastern Roman Empire, it extends to the 15th century.",
        "beta": 1.5,
        "topic": "history",
        "concept": "Roman Empire"
    },
    # More questions for variety
    {
        "text": "What river forms the delta in northern Egypt?",
        "options": ["Nile", "Tigris", "Euphrates", "Jordan"],
        "correct_index": 0,
        "explanation": "The Nile Delta is one of the world's largest river deltas, crucial for Egyptian agriculture.",
        "hint": "This is one of the most famous rivers in Africa.",
        "beta": -1.5,
        "topic": "geography",
        "concept": "Nile River Delta"
    },
    {
        "text": "What type of biome characterizes the Siberian Tundra?",
        "options": ["Treeless frozen plain", "Dense forest", "Grassland", "Desert"],
        "correct_index": 0,
        "explanation": "Tundra is characterized by permafrost, low temperatures, and lack of trees.",
        "hint": "The soil here is permanently frozen below the surface.",
        "beta": 0.5,
        "topic": "geography",
        "concept": "Siberian Tundra"
    },
    {
        "text": "What is the primary threat to the Great Barrier Reef?",
        "options": ["Coral bleaching from warming", "Overfishing", "Oil spills", "Plastic pollution"],
        "correct_index": 0,
        "explanation": "Rising ocean temperatures cause coral bleaching, the greatest threat to the reef's survival.",
        "hint": "This threat is related to climate change and water temperature.",
        "beta": 0.5,
        "topic": "geography",
        "concept": "Great Barrier Reef"
    },
    {
        "text": "Which Greek city-state was known for its military culture?",
        "options": ["Sparta", "Athens", "Corinth", "Delphi"],
        "correct_index": 0,
        "explanation": "Sparta was famous for its military-focused society and powerful army.",
        "hint": "The movie '300' was about warriors from this city.",
        "beta": -1.0,
        "topic": "history",
        "concept": "Greek City-States"
    },
    {
        "text": "What was the primary religion of the Ottoman Empire?",
        "options": ["Islam", "Christianity", "Judaism", "Zoroastrianism"],
        "correct_index": 0,
        "explanation": "The Ottoman Empire was an Islamic caliphate, though it tolerated other religions.",
        "hint": "The Sultan held the title of Caliph in this faith.",
        "beta": -1.0,
        "topic": "history",
        "concept": "Ottoman Empire"
    },
    {
        "text": "What made the Persian Empire notable in terms of governance?",
        "options": ["Religious tolerance", "Military aggression", "Isolationism", "Democracy"],
        "correct_index": 0,
        "explanation": "The Persian Empire was known for allowing conquered peoples to keep their customs and religions.",
        "hint": "Cyrus the Great was respected for this approach to ruling diverse peoples.",
        "beta": 0.5,
        "topic": "history",
        "concept": "Persian Empire"
    },
    {
        "text": "What engineering feat connected the Mediterranean and Red Sea in ancient times?",
        "options": ["Ancient canal (precursor to Suez)", "Mountain tunnel", "Bridge system", "Underground waterway"],
        "correct_index": 0,
        "explanation": "Ancient Egyptians built canals connecting the Nile to the Red Sea as early as the 19th century BCE.",
        "hint": "This predates the modern Suez Canal by thousands of years.",
        "beta": 2.0,
        "topic": "geography",
        "concept": "Mediterranean Sea"
    },
    {
        "text": "What mountain range separates Siberia from European Russia?",
        "options": ["Ural Mountains", "Caucasus", "Alps", "Carpathians"],
        "correct_index": 0,
        "explanation": "The Ural Mountains form the traditional boundary between Europe and Asia.",
        "hint": "These mountains run north-south through Russia.",
        "beta": 0.5,
        "topic": "geography",
        "concept": "Siberian Tundra"
    },
    {
        "text": "Which Byzantine emperor codified Roman law?",
        "options": ["Justinian I", "Constantine I", "Theodosius I", "Heraclius"],
        "correct_index": 0,
        "explanation": "Justinian I created the Corpus Juris Civilis, the foundation of modern civil law.",
        "hint": "He also built the Hagia Sophia.",
        "beta": 1.5,
        "topic": "history",
        "concept": "Byzantine Empire"
    },
    {
        "text": "How high is Mount Everest above sea level?",
        "options": ["8,849 meters", "8,611 meters", "8,586 meters", "8,516 meters"],
        "correct_index": 0,
        "explanation": "Mount Everest's official height is 8,849 meters (29,032 feet) as of 2020.",
        "hint": "It's just under 9,000 meters.",
        "beta": 1.0,
        "topic": "geography",
        "concept": "Himalayan Range"
    },
]


# ────────────────────────────────────────────────────────────────────────────
# TEST USERS
# ────────────────────────────────────────────────────────────────────────────
TEST_PASSWORD = "TestPass123!"

# More detailed test users with clear specializations for testing IRT adaptation
TEST_USERS = [
    {
        "email": "geo_expert@test.com",
        "username": "geo_expert",
        "elo_global": 1.8,
        "profile": "Geography master (500+ questions), struggles with history",
        "points": 2500,
        "level": "Expert",
        # Per-concept mastery - geography concepts they've mastered
        "concept_mastery": {
            # Geography concepts - HIGH mastery (theta 1.5-2.5)
            "Amazon River Basin": {"theta": 2.2, "responses": 80, "accuracy": 0.92},
            "Sahara Desert": {"theta": 2.0, "responses": 75, "accuracy": 0.88},
            "Himalayan Range": {"theta": 1.8, "responses": 60, "accuracy": 0.85},
            "Mediterranean Sea": {"theta": 2.5, "responses": 90, "accuracy": 0.95},
            "Great Barrier Reef": {"theta": 1.9, "responses": 55, "accuracy": 0.87},
            "Arctic Circle": {"theta": 1.6, "responses": 45, "accuracy": 0.82},
            "Nile River Delta": {"theta": 2.1, "responses": 70, "accuracy": 0.90},
            "Siberian Tundra": {"theta": 1.5, "responses": 40, "accuracy": 0.80},
            # History concepts - LOW mastery (theta -1.5 to 0)
            "Egyptian Empire": {"theta": -0.5, "responses": 15, "accuracy": 0.45},
            "Roman Empire": {"theta": -1.0, "responses": 12, "accuracy": 0.35},
            "Mongol Empire": {"theta": 0.0, "responses": 18, "accuracy": 0.50},
            "Ottoman Empire": {"theta": -1.2, "responses": 10, "accuracy": 0.30},
            "Byzantine Empire": {"theta": -0.8, "responses": 8, "accuracy": 0.40},
            "Greek City-States": {"theta": -0.3, "responses": 14, "accuracy": 0.48},
            "Persian Empire": {"theta": -1.5, "responses": 6, "accuracy": 0.25},
        },
    },
    {
        "email": "hist_expert@test.com",
        "username": "hist_expert",
        "elo_global": 1.6,
        "profile": "History scholar (450+ questions), weak in geography",
        "points": 2200,
        "level": "Expert",
        "concept_mastery": {
            # History concepts - HIGH mastery
            "Egyptian Empire": {"theta": 2.3, "responses": 85, "accuracy": 0.93},
            "Roman Empire": {"theta": 2.5, "responses": 95, "accuracy": 0.96},
            "Mongol Empire": {"theta": 1.8, "responses": 55, "accuracy": 0.85},
            "Ottoman Empire": {"theta": 2.0, "responses": 65, "accuracy": 0.88},
            "Byzantine Empire": {"theta": 2.2, "responses": 75, "accuracy": 0.91},
            "Greek City-States": {"theta": 1.9, "responses": 60, "accuracy": 0.87},
            "Persian Empire": {"theta": 1.7, "responses": 50, "accuracy": 0.84},
            # Geography concepts - LOW mastery
            "Amazon River Basin": {"theta": -1.0, "responses": 10, "accuracy": 0.35},
            "Sahara Desert": {"theta": -0.5, "responses": 12, "accuracy": 0.42},
            "Himalayan Range": {"theta": -1.2, "responses": 8, "accuracy": 0.30},
            "Mediterranean Sea": {"theta": 0.0, "responses": 15, "accuracy": 0.50},
            "Great Barrier Reef": {"theta": -0.8, "responses": 9, "accuracy": 0.38},
            "Arctic Circle": {"theta": -1.5, "responses": 5, "accuracy": 0.22},
            "Nile River Delta": {"theta": -0.3, "responses": 11, "accuracy": 0.45},
            "Siberian Tundra": {"theta": -1.3, "responses": 6, "accuracy": 0.28},
        },
    },
    {
        "email": "balanced@test.com",
        "username": "balanced",
        "elo_global": 0.5,
        "profile": "Well-rounded learner (200+ questions), moderate in both topics",
        "points": 800,
        "level": "Intermediate",
        "concept_mastery": {
            # All concepts around theta 0 (±0.5)
            "Amazon River Basin": {"theta": 0.3, "responses": 25, "accuracy": 0.58},
            "Sahara Desert": {"theta": 0.1, "responses": 22, "accuracy": 0.54},
            "Himalayan Range": {"theta": -0.2, "responses": 18, "accuracy": 0.48},
            "Mediterranean Sea": {"theta": 0.4, "responses": 28, "accuracy": 0.60},
            "Great Barrier Reef": {"theta": 0.0, "responses": 20, "accuracy": 0.52},
            "Arctic Circle": {"theta": -0.3, "responses": 15, "accuracy": 0.46},
            "Nile River Delta": {"theta": 0.2, "responses": 24, "accuracy": 0.56},
            "Siberian Tundra": {"theta": -0.1, "responses": 16, "accuracy": 0.50},
            "Egyptian Empire": {"theta": 0.5, "responses": 30, "accuracy": 0.62},
            "Roman Empire": {"theta": 0.3, "responses": 26, "accuracy": 0.58},
            "Mongol Empire": {"theta": -0.2, "responses": 19, "accuracy": 0.47},
            "Ottoman Empire": {"theta": 0.1, "responses": 21, "accuracy": 0.53},
            "Byzantine Empire": {"theta": 0.0, "responses": 17, "accuracy": 0.51},
            "Greek City-States": {"theta": 0.4, "responses": 27, "accuracy": 0.59},
            "Persian Empire": {"theta": -0.1, "responses": 14, "accuracy": 0.49},
        },
    },
    {
        "email": "beginner@test.com",
        "username": "beginner",
        "elo_global": 0.0,
        "profile": "Brand new user - cold start (0 questions)",
        "points": 0,
        "level": "Novice",
        "concept_mastery": {},  # No records - cold start user
    },
    {
        "email": "challenger@test.com",
        "username": "challenger",
        "elo_global": 1.2,
        "profile": "Challenge mode specialist (300+ questions), rank Silver → Gold",
        "points": 1500,
        "level": "Advanced",
        "concept_mastery": {
            # Mixed mastery - some strong, some weak
            "Amazon River Basin": {"theta": 1.2, "responses": 35, "accuracy": 0.78},
            "Sahara Desert": {"theta": 0.8, "responses": 28, "accuracy": 0.68},
            "Himalayan Range": {"theta": 1.5, "responses": 42, "accuracy": 0.82},
            "Mediterranean Sea": {"theta": 0.5, "responses": 22, "accuracy": 0.60},
            "Great Barrier Reef": {"theta": 1.0, "responses": 30, "accuracy": 0.72},
            "Arctic Circle": {"theta": -0.5, "responses": 12, "accuracy": 0.42},
            "Nile River Delta": {"theta": 0.3, "responses": 18, "accuracy": 0.55},
            "Siberian Tundra": {"theta": -0.2, "responses": 14, "accuracy": 0.48},
            "Egyptian Empire": {"theta": 1.3, "responses": 38, "accuracy": 0.79},
            "Roman Empire": {"theta": 1.0, "responses": 32, "accuracy": 0.73},
            "Mongol Empire": {"theta": 0.7, "responses": 25, "accuracy": 0.65},
            "Ottoman Empire": {"theta": -0.3, "responses": 15, "accuracy": 0.46},
            "Byzantine Empire": {"theta": 0.4, "responses": 20, "accuracy": 0.58},
            "Greek City-States": {"theta": 1.1, "responses": 34, "accuracy": 0.76},
            "Persian Empire": {"theta": 0.0, "responses": 16, "accuracy": 0.50},
        },
        "challenge": {"rank_id": 2, "wins": 12, "losses": 4, "skip_attempts": 2},
    },
    {
        "email": "struggling@test.com",
        "username": "struggling",
        "elo_global": -1.0,
        "profile": "Struggling learner (100+ questions), needs easier content",
        "points": 150,
        "level": "Novice",
        "concept_mastery": {
            # All concepts LOW mastery (theta -1.5 to -0.5)
            "Amazon River Basin": {"theta": -1.0, "responses": 12, "accuracy": 0.32},
            "Sahara Desert": {"theta": -0.8, "responses": 10, "accuracy": 0.38},
            "Himalayan Range": {"theta": -1.2, "responses": 8, "accuracy": 0.28},
            "Mediterranean Sea": {"theta": -0.6, "responses": 14, "accuracy": 0.42},
            "Great Barrier Reef": {"theta": -1.5, "responses": 6, "accuracy": 0.22},
            "Arctic Circle": {"theta": -1.8, "responses": 4, "accuracy": 0.18},
            "Nile River Delta": {"theta": -0.9, "responses": 11, "accuracy": 0.35},
            "Siberian Tundra": {"theta": -1.3, "responses": 7, "accuracy": 0.26},
            "Egyptian Empire": {"theta": -0.5, "responses": 15, "accuracy": 0.45},
            "Roman Empire": {"theta": -0.7, "responses": 13, "accuracy": 0.40},
            "Mongol Empire": {"theta": -1.0, "responses": 9, "accuracy": 0.33},
            "Ottoman Empire": {"theta": -1.4, "responses": 5, "accuracy": 0.24},
            "Byzantine Empire": {"theta": -1.1, "responses": 8, "accuracy": 0.30},
            "Greek City-States": {"theta": -0.6, "responses": 12, "accuracy": 0.41},
            "Persian Empire": {"theta": -1.6, "responses": 3, "accuracy": 0.20},
        },
    },
    {
        "email": "inactive@test.com",
        "username": "inactive",
        "elo_global": 1.0,
        "profile": "Inactive for 30 days - tests decay feature",
        "points": 600,
        "level": "Scholar",
        # This user was good at geography but hasn't played in a month
        # Their theta should decay when they return
        "concept_mastery": {
            # Note: These thetas will be set, but seed script will need to
            # set last_updated to 30 days ago for decay testing
            "Amazon River Basin": {"theta": 1.5, "responses": 40, "accuracy": 0.80},
            "Sahara Desert": {"theta": 1.2, "responses": 35, "accuracy": 0.75},
            "Himalayan Range": {"theta": 1.0, "responses": 30, "accuracy": 0.70},
            "Mediterranean Sea": {"theta": 0.8, "responses": 25, "accuracy": 0.65},
            "Egyptian Empire": {"theta": 0.5, "responses": 20, "accuracy": 0.60},
            "Roman Empire": {"theta": 0.3, "responses": 15, "accuracy": 0.55},
        },
        "inactive_days": 30,  # Special flag for this user
    },
]


async def seed_concepts(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed concepts and return name→id mapping."""
    concept_map = {}
    
    for c in GEOGRAPHY_CONCEPTS:
        existing = await db.execute(
            select(Concept).where(Concept.name == c["name"])
        )
        concept = existing.scalar_one_or_none()
        if not concept:
            concept = Concept(
                id=uuid.uuid4(),
                name=c["name"],
                topic="geography",
                description=c["description"],
                created_at=utc_now(),
            )
            db.add(concept)
            logger.info(f"Created concept: {c['name']} (geography)")
        concept_map[c["name"]] = concept.id
    
    for c in HISTORY_CONCEPTS:
        existing = await db.execute(
            select(Concept).where(Concept.name == c["name"])
        )
        concept = existing.scalar_one_or_none()
        if not concept:
            concept = Concept(
                id=uuid.uuid4(),
                name=c["name"],
                topic="history",
                description=c["description"],
                created_at=utc_now(),
            )
            db.add(concept)
            logger.info(f"Created concept: {c['name']} (history)")
        concept_map[c["name"]] = concept.id
    
    await db.flush()
    
    # Re-fetch to get IDs for existing concepts
    all_concepts = await db.execute(select(Concept))
    for concept in all_concepts.scalars().all():
        concept_map[concept.name] = concept.id
    
    return concept_map


async def seed_questions(db: AsyncSession, concept_map: dict[str, uuid.UUID]) -> list[uuid.UUID]:
    """Seed questions and return list of question IDs."""
    question_ids = []
    
    for q in QUESTIONS:
        # Check if question already exists (by text)
        existing = await db.execute(
            select(QuestionBank).where(QuestionBank.question_text == q["text"])
        )
        question = existing.scalar_one_or_none()
        
        if not question:
            concept_id = concept_map.get(q["concept"])
            question = QuestionBank(
                id=uuid.uuid4(),
                question_text=q["text"],
                correct_answer=q["options"][q["correct_index"]],
                options_json=json.dumps(q["options"]),
                explanation=q["explanation"],
                hint=q["hint"],
                topic=q["topic"],
                difficulty_irt=q["beta"],
                discrimination=1.0,
                usage_count=0,
                times_seen=0,
                source="seed",
                primary_concept_id=concept_id,
                created_at=utc_now(),
            )
            db.add(question)
            
            # Create question-concept link
            if concept_id:
                link = QuestionConcept(
                    id=uuid.uuid4(),
                    question_id=question.id,
                    concept_id=concept_id,
                    is_primary=True,
                    created_at=utc_now(),
                )
                db.add(link)
            
            logger.info(f"Created question: {q['text'][:50]}... (β={q['beta']})")
        
        question_ids.append(question.id)
    
    await db.flush()
    return question_ids


async def seed_users(
    db: AsyncSession,
    concept_map: dict[str, uuid.UUID],
    question_ids: list[uuid.UUID]
) -> None:
    """Seed test users with concept thetas and response history."""
    password_hash = hash_password(TEST_PASSWORD)
    
    # Get concept IDs by topic
    geo_concepts = [cid for name, cid in concept_map.items() 
                    if name in [c["name"] for c in GEOGRAPHY_CONCEPTS]]
    hist_concepts = [cid for name, cid in concept_map.items() 
                     if name in [c["name"] for c in HISTORY_CONCEPTS]]
    
    for u in TEST_USERS:
        # Check if user exists
        existing = await db.execute(
            select(User).where(User.email == u["email"])
        )
        user = existing.scalar_one_or_none()
        
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=u["email"],
                username=u["username"],
                password_hash=password_hash,
                points=u.get("points", 100),
                level=u.get("level", "Novice"),
                elo_global=u["elo_global"],
                created_at=utc_now() - timedelta(days=60),  # Older accounts
                last_login=utc_now() - timedelta(hours=2),
                is_active=True,
            )
            db.add(user)
            await db.flush()
            logger.info(f"Created user: {u['username']} (elo={u['elo_global']}, points={u.get('points', 100)})")
        
        # Create concept thetas based on new detailed mastery data
        concept_mastery = u.get("concept_mastery", {})
        
        if concept_mastery:
            total_responses = 0
            for concept_name, mastery in concept_mastery.items():
                concept_id = concept_map.get(concept_name)
                if not concept_id:
                    logger.warning(f"Concept not found: {concept_name}")
                    continue
                
                # Check if theta record already exists
                existing_theta = await db.execute(
                    select(UserConceptTheta).where(
                        (UserConceptTheta.user_id == user.id) &
                        (UserConceptTheta.concept_id == concept_id)
                    )
                )
                if existing_theta.scalar_one_or_none():
                    continue
                
                now = utc_now()
                responses = mastery["responses"]
                theta_val = mastery["theta"]
                total_responses += responses
                
                # Calculate variance (lower variance = more confident)
                # More responses = lower variance
                variance = max(0.1, 1.0 / (1.0 + responses * 0.05))
                
                # Determine mastery level and state based on theta
                if theta_val >= 1.5:
                    mastery_level = "ADVANCED"
                    concept_state = "MASTERED"
                elif theta_val >= 0.5:
                    mastery_level = "PROFICIENT"
                    concept_state = "LEARNING"
                elif theta_val >= -0.5:
                    mastery_level = "LEARNING"
                    concept_state = "LEARNING"
                else:
                    mastery_level = "BEGINNER"
                    concept_state = "EXPLORING"
                
                # Handle inactive user - set last_updated in the past
                inactive_days = u.get("inactive_days", 0)
                if inactive_days > 0:
                    last_updated_date = now - timedelta(days=inactive_days)
                    last_played_date = now - timedelta(days=inactive_days)
                else:
                    last_updated_date = now - timedelta(days=1)
                    last_played_date = now - timedelta(days=1)
                
                # Create theta record
                theta_record = UserConceptTheta(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    concept_id=concept_id,
                    theta=theta_val,
                    theta_variance=variance,
                    response_count=responses,
                    exposure_count=int(responses * 1.2),  # Slightly more exposures than responses
                    first_seen_at=now - timedelta(days=responses // 2),  # Older if more responses
                    last_updated=last_updated_date,
                    created_at=now - timedelta(days=responses // 2),
                    mastery_level=mastery_level,
                    last_played_at=last_played_date,
                    updated_at=now,
                    concept_state=concept_state,
                )
                db.add(theta_record)
            
            logger.info(f"  → Created {len(concept_mastery)} concept thetas for {u['username']}")
        
        # Create challenge rank for challenger user
        if "challenge" in u:
            existing_rank = await db.execute(
                select(UserChallengeRank).where(UserChallengeRank.user_id == user.id)
            )
            if not existing_rank.scalar_one_or_none():
                rank = UserChallengeRank(
                    user_id=user.id,
                    current_rank_id=u["challenge"]["rank_id"],
                    wins=u["challenge"]["wins"],
                    losses=u["challenge"]["losses"],
                    skip_attempts_remaining=u["challenge"].get("skip_attempts", 3),
                )
                db.add(rank)
                logger.info(f"  → Created challenge rank for {u['username']}: rank {u['challenge']['rank_id']}")
        
        # Create detailed response history based on concept mastery
        if concept_mastery:
            session_id = uuid.uuid4()  # Single session for this user's history
            response_count = 0
            
            for concept_name, mastery in concept_mastery.items():
                concept_id = concept_map.get(concept_name)
                if not concept_id:
                    continue
                
                # Find questions for this concept
                concept_questions = [
                    q for q in QUESTIONS 
                    if q["concept"] == concept_name
                ]
                if not concept_questions:
                    continue
                
                # Generate responses based on accuracy
                num_responses = mastery["responses"]
                accuracy = mastery["accuracy"]
                theta_val = mastery["theta"]
                
                # Determine topic from concept
                topic = "geography" if concept_name in [c["name"] for c in GEOGRAPHY_CONCEPTS] else "history"
                
                for i in range(num_responses):
                    # Select question (cycle through available)
                    q_data = concept_questions[i % len(concept_questions)]
                    
                    # Find the question ID
                    q_result = await db.execute(
                        select(QuestionBank).where(QuestionBank.question_text == q_data["text"])
                    )
                    question = q_result.scalar_one_or_none()
                    if not question:
                        continue
                    
                    # Simulate correctness based on accuracy (with some randomness)
                    # Higher theta = more likely to get hard questions right
                    random.seed(hash(f"{user.id}{concept_name}{i}"))
                    correct = random.random() < accuracy
                    
                    # Calculate difficulty sent based on theta
                    difficulty_sent = max(1, min(5, int(3 + theta_val)))
                    
                    # Time varies - experts are faster
                    base_time = 25 - int(theta_val * 3)  # Experts faster
                    time_taken = max(5, base_time + random.randint(-5, 10))
                    
                    # Hint usage - lower theta users use more hints
                    used_hint = random.random() < max(0.1, 0.4 - theta_val * 0.1)
                    
                    response = UserResponse(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        session_id=session_id,
                        question_id=question.id,
                        topic=topic,
                        difficulty_sent=difficulty_sent,
                        answered_correct=correct,
                        time_taken=time_taken,
                        used_hint=used_hint,
                        created_at=utc_now() - timedelta(days=num_responses - i, hours=random.randint(0, 23)),
                    )
                    db.add(response)
                    response_count += 1
            
            logger.info(f"  → Created {response_count} response records for {u['username']}")
    
    await db.flush()


async def seed_challenge_ranks(db: AsyncSession) -> None:
    """Ensure challenge ranks exist (they're seeded in migration, but just in case)."""
    existing = await db.execute(select(ChallengeRank))
    if existing.scalars().first():
        logger.info("Challenge ranks already exist")
        return
    
    ranks = [
        ChallengeRank(id=1, name="Bronze", min_elo=0.0, n_options=2, has_timer=False, timer_seconds=None),
        ChallengeRank(id=2, name="Silver", min_elo=0.5, n_options=4, has_timer=False, timer_seconds=None),
        ChallengeRank(id=3, name="Gold", min_elo=1.0, n_options=4, has_timer=True, timer_seconds=45),
        ChallengeRank(id=4, name="Platinum", min_elo=1.5, n_options=4, has_timer=True, timer_seconds=30),
        ChallengeRank(id=5, name="Diamond", min_elo=2.0, n_options=4, has_timer=True, timer_seconds=25),
    ]
    for r in ranks:
        db.add(r)
    await db.flush()
    logger.info("Created challenge ranks")


async def seed_all(session_factory=None):
    """
    Seed the database with initial data.
    
    Can be called from main.py with a session factory, or standalone.
    """
    logger.info("=" * 60)
    logger.info("AdaptIQ Seed Script")
    logger.info("=" * 60)
    
    if session_factory is None:
        # Standalone mode: create our own session
        async with get_async_session_context() as db:
            await _run_seed(db)
    else:
        # Called from main.py with existing session factory
        async with session_factory() as db:
            await _run_seed(db)


async def _run_seed(db: AsyncSession):
    """Internal seed logic."""
    # Seed in order
    logger.info("\n1. Seeding concepts...")
    concept_map = await seed_concepts(db)
    logger.info(f"   → {len(concept_map)} concepts ready")

    logger.info("\n2. Seeding questions...")
    question_ids = await seed_questions(db, concept_map)
    logger.info(f"   → {len(question_ids)} questions ready")

    logger.info("\n3. Seeding challenge ranks...")
    await seed_challenge_ranks(db)

    logger.info("\n4. Seeding Custom Room facts...")
    from seeds.custom_room_facts import seed_custom_room_facts
    await seed_custom_room_facts(db)

    logger.info("\n5. Seeding test users...")
    await seed_users(db, concept_map, question_ids)
    logger.info(f"   → {len(TEST_USERS)} users ready")

    await db.commit()

    logger.info("\n" + "=" * 60)
    logger.info("Seed complete!")
    logger.info("=" * 60)
    logger.info("\nTest user credentials (password: TestPass123!):")
    for u in TEST_USERS:
        logger.info(f"  - {u['email']} ({u['profile']})")


async def main():
    logger.info("=" * 60)
    logger.info("AdaptIQ Seed Script")
    logger.info("=" * 60)
    
    async with get_async_session_context() as db:
        # First ensure schema is up to date
        logger.info("\n0. Checking database schema...")
        await ensure_schema(db)
        
        # Seed in order
        logger.info("\n1. Seeding concepts...")
        concept_map = await seed_concepts(db)
        logger.info(f"   → {len(concept_map)} concepts ready")
        
        logger.info("\n2. Seeding questions...")
        question_ids = await seed_questions(db, concept_map)
        logger.info(f"   → {len(question_ids)} questions ready")
        
        logger.info("\n3. Seeding challenge ranks...")
        await seed_challenge_ranks(db)
        
        logger.info("\n4. Seeding test users...")
        await seed_users(db, concept_map, question_ids)
        logger.info(f"   → {len(TEST_USERS)} users ready")
        
        await db.commit()
        
    logger.info("\n" + "=" * 60)
    logger.info("Seed complete!")
    logger.info("=" * 60)
    logger.info("\nTest user credentials (password: TestPass123!):")
    for u in TEST_USERS:
        logger.info(f"  - {u['email']} ({u['profile']})")


if __name__ == "__main__":
    asyncio.run(main())
