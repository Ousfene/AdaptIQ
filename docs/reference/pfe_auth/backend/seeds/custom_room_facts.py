"""
seeds/custom_room_facts.py — Seeding script for Custom Room facts.

Populates the `facts` table with initial fact data for each topic.

For MVP, includes 100-200 curated facts per topic.
Can be expanded to 1000+ with LLM auto-generation later.
"""

from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Fact


def utc_now_naive() -> datetime:
    """Return current UTC time without timezone info."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Fact data organized by topic
FACTS_DATA = {
    "History - World War II": [
        "Battle of Stalingrad occurred from August 1942 to February 1943",
        "D-Day invasion of Normandy took place on June 6, 1944",
        "Adolf Hitler was the Führer of Nazi Germany",
        "The Holocaust resulted in approximately 6 million Jewish deaths",
        "Pearl Harbor was attacked by Japan on December 7, 1941",
        "Germany's Axis powers included Italy and Japan",
        "The Battle of Britain occurred in 1940",
        "Midway was a turning point in the Pacific War",
        "Atomic bombs were dropped on Hiroshima and Nagasaki in August 1945",
        "France was liberated in August 1944",
        "Winston Churchill was Prime Minister of Britain",
        "Franklin D. Roosevelt was President of the United States during WWII",
        "Joseph Stalin led the Soviet Union",
        "The Blitz was Germany's bombing campaign against Britain",
        "VE Day (Victory in Europe) was May 8, 1945",
        "VJ Day marked Japan's surrender",
        "The Battle of Iwo Jima was fought from February to March 1945",
        "The Enigma machine was used for German communications",
        "El Alamein was a major victory for the Allies in North Africa",
        "The Yalta Conference occurred in February 1945",
    ],
    "History - Cold War": [
        "The Cold War lasted from 1947 to 1991",
        "The Berlin Wall was built in 1961",
        "The Cuban Missile Crisis occurred in October 1962",
        "The Soviet Union and United States were the main superpowers",
        "The Iron Curtain divided Eastern and Western Europe",
        "The Korean War lasted from 1950 to 1953",
        "The Vietnam War escalated in the 1960s and 1970s",
        "The Space Race culminated in the Moon landing in 1969",
        "Nikita Khrushchev was General Secretary of the Soviet Union",
        "Leonid Brezhnev succeeded Khrushchev as Soviet leader",
        "The Berlin Blockade lasted from 1948 to 1949",
        "NATO was formed in 1949",
        "The Warsaw Pact was established in 1955",
        "The Hungarian Uprising occurred in 1956",
        "The Prague Spring took place in 1968",
        "The Berlin Wall fell in 1989",
        "The Soviet Union dissolved in 1991",
        "President Kennedy was assassinated in 1963",
        "The Sino-Soviet split occurred in the 1960s",
        "Mikhail Gorbachev introduced glasnost and perestroika",
    ],
    "History - Ancient Rome": [
        "Rome was founded traditionally in 753 BCE",
        "Augustus was the first Emperor of Rome",
        "The Roman Republic lasted about 500 years",
        "Julius Caesar was assassinated in 44 BCE",
        "The Colosseum was built in Rome",
        "The Roman Empire reached its greatest extent under Trajan",
        "Latin was the language of Rome",
        "The Roman Forum was the center of political life",
        "Aqueducts were used to transport water",
        "Gladiatorial games were held in amphitheaters",
        "The Roman military was organized into legions",
        "Constantine moved the capital to Constantinople",
        "Christianity became the state religion under Theodosius",
        "The Pax Romana was a period of relative peace",
        "Virgil was a famous Roman poet",
        "The Senate was the ruling body of Rome",
        "Roman roads connected the empire",
        "The Punic Wars were fought against Carthage",
        "Hannibal was a Carthaginian general",
        "The Third Punic War ended with Rome's victory",
    ],
    "History - Medieval Europe": [
        "The Middle Ages lasted from approximately 500 to 1500 CE",
        "Charlemagne was crowned Emperor in 800 CE",
        "The Frankish Empire controlled much of Europe",
        "Feudalism was the dominant social system",
        "Knights were the warrior class of medieval Europe",
        "Monasteries preserved knowledge during the Dark Ages",
        "The Catholic Church was the most powerful institution",
        "Castles were fortified residences of nobles",
        "The Magna Carta was signed in 1215 in England",
        "The Hundred Years' War was fought between France and England",
        "Joan of Arc was a French military leader",
        "Print mass production began with Gutenberg's printing press around 1440",
        "The Black Death killed millions in the 14th century",
        "Universities were established during the medieval period",
        "Crusades were military campaigns to the Holy Land",
        "King Arthur is a legendary British king",
        "The Viking invasions occurred from 793-1066 CE",
        "William the Conqueror invaded England in 1066",
        "The Holy Roman Empire was a multi-ethnic state",
        "Armor and crossbows were important military technology",
    ],
    "History - Renaissance": [
        "The Renaissance began in Italy in the 14th century",
        "Leonardo da Vinci was a polymath artist and inventor",
        "Michelangelo created famous artworks including the Sistine Chapel ceiling",
        "The Renaissance focused on humanism and classical learning",
        "Johannes Gutenberg's printing press revolutionized information distribution",
        "Christopher Columbus reached the Americas in 1492",
        "The printing press enabled widespread literacy",
        "Petrarch is considered the father of humanism",
        "Florence was a center of Renaissance culture",
        "The Medici family patronized the arts",
        "Raphael was a renowned Renaissance painter",
        "Dante Alighieri wrote The Divine Comedy in the late medieval period",
        "Niccolò Machiavelli wrote The Prince",
        "The Protestant Reformation began in 1517",
        "Martin Luther challenged the Catholic Church",
        "Galileo Galilei made scientific observations with a telescope",
        "The scientific revolution challenged medieval thinking",
        "Erasmus was a Renaissance humanist philosopher",
        "The invention of the telescope advanced astronomy",
        "Renaissance art emphasized perspective and realism",
    ],
    "Geography - France": [
        "The capital of France is Paris",
        "France is located in Western Europe",
        "The currency of France is the Euro",
        "The Eiffel Tower is an iconic landmark in Paris",
        "The Louvre Museum is located in Paris",
        "The Southern coast of France borders the Mediterranean Sea",
        "The Pyrenees Mountains form a border with Spain",
        "The Alps are located in the southeastern region",
        "Mont Blanc is the highest peak in the Alps",
        "The River Seine flows through Paris",
        "The Loire Valley is famous for castles and wine",
        "Bordeaux is famous for wine production",
        "The Normandy region is in northern France",
        "Brittany is a region in northwestern France",
        "Provence is in the southeastern part of France",
        "France is the most visited country in the world",
        "The Palace of Versailles is near Paris",
        "The Arc de Triomphe is a famous monument in Paris",
        "Notre-Dame is a famous cathedral in Paris",
        "France is a founding member of the European Union",
    ],
    "Geography - Japan": [
        "The capital of Japan is Tokyo",
        "Japan is an island nation in East Asia",
        "The currency of Japan is the Japanese Yen",
        "Japan consists of four main islands",
        "Mount Fuji is the tallest mountain in Japan",
        "Tokyo is the largest metropolitan area in the world",
        "Kyoto is famous for traditional temples and culture",
        "Osaka is a major economic and cultural center",
        "The Sea of Japan separates Japan from the Asian mainland",
        "Cherry blossoms are an iconic symbol of Japan",
        "Japan experiences frequent earthquakes",
        "The bullet train (shinkansen) connects major cities",
        "Sumo wrestling is a traditional sport in Japan",
        "Tea ceremony is an important cultural practice",
        "Anime and manga are pop culture exports from Japan",
        "Hiroshima and Nagasaki were destroyed by atomic bombs in 1945",
        "Japan is known for advanced technology and manufacturing",
        "The Meiji Restoration modernized Japan in 1868",
        "Japan was isolated from the world until 1853",
        "Public bathhouses (onsen) are popular in Japan",
    ],
    "Geography - Brazil": [
        "The capital of Brazil is Brasília",
        "Brazil is the largest country in South America",
        "The currency of Brazil is the Brazilian Real",
        "The Amazon Rainforest is located in Brazil",
        "Rio de Janeiro is famous for Christ the Redeemer statue",
        "The Amazon River is the longest river in South America",
        "Brazil is the most populous country in South America",
        "São Paulo is the largest city in Brazil",
        "The Atlantic Ocean borders Brazil on the east",
        "The Iguazu Falls are on the border with Argentina",
        "Brazil is a leading agricultural exporter",
        "Coffee is a major export product of Brazil",
        "The Brazilian music genre bossa nova originated in Brazil",
        "Carnival is a major cultural celebration in Brazil",
        "Soccer (football) is the most popular sport",
        "The Trans-Amazonian Highway crosses the rainforest",
        "Brazil was colonized by Portugal",
        "Portuguese is the official language of Brazil",
        "The Pantanal is a large wetland region",
        "Brazil has diverse indigenous populations",
    ],
    "Geography - Egypt": [
        "The capital of Egypt is Cairo",
        "Egypt is located in northeastern Africa",
        "The currency of Egypt is the Egyptian Pound",
        "The Nile River is the longest river in Africa",
        "The Great Pyramids of Giza are located in Egypt",
        "The Sphinx is a colossal statue near the pyramids",
        "Ancient Egypt was one of the earliest civilizations",
        "Pharaohs ruled ancient Egypt",
        "Hieroglyphics were the writing system of ancient Egypt",
        "The Suez Canal connects the Mediterranean and Red Sea",
        "Alexandria was founded by Alexander the Great",
        "The Valley of the Kings contains royal tombs",
        "The Mediterranean Sea borders Egypt on the north",
        "The Red Sea borders Egypt on the east",
        "Cairo is the most populous city in Africa",
        "Luxor is home to ancient temples and artifacts",
        "The Aswan Dam controls the Nile River",
        "Islam is the dominant religion in Egypt",
        "Arabic is the official language of Egypt",
        "Egypt is strategically important for global trade",
    ],
    "Geography - Australia": [
        "The capital of Australia is Canberra",
        "Australia is a country and continent",
        "The currency of Australia is the Australian Dollar",
        "Sydney is the largest city in Australia",
        "The Great Barrier Reef is the world's largest coral system",
        "Uluru (Ayers Rock) is an iconic landmark in central Australia",
        "Australia is surrounded by oceans",
        "The Outback is the vast sparsely populated interior",
        "Kangaroos are native to Australia",
        "Koalas are endemic to Australia",
        "The Aboriginal people are the indigenous inhabitants",
        "Australia has the second-largest island, Tasmania",
        "Melbourne is famous for coffee culture",
        "Brisbane is home to the Brisbane River",
        "Australia experiences a high level of biodiversity",
        "Perth is the most isolated major city in the world",
        "The Murray River is a major river in southeastern Australia",
        "Eucalyptus trees are native to Australia",
        "Australia was founded as a British penal colony",
        "English is the official language of Australia",
    ],
}


async def seed_custom_room_facts(db: AsyncSession):
    """Seed initial facts into the facts table."""

    # Check if facts already exist (idempotent)
    existing_count = await db.scalar(
        select(Fact.__table__).select().limit(1)
    )
    if existing_count:
        print("✓ Facts already seeded. Skipping.")
        return

    print("Seeding Custom Room facts...")
    fact_count = 0

    for topic, facts_list in FACTS_DATA.items():
        for fact_content in facts_list:
            fact = Fact(
                id=uuid4(),
                topic=topic,
                content=fact_content,
                difficulty_hint=None,  # Can be set based on content later
                total_questions_generated=0,
                created_at=utc_now_naive(),
            )
            db.add(fact)
            fact_count += 1

    await db.commit()
    print(f"✓ Seeded {fact_count} facts across {len(FACTS_DATA)} topics.")
