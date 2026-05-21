import React, { useEffect, useState } from 'react';
import { Loader2, AlertTriangle } from 'lucide-react';
import { ConceptBreakdown, ConceptMastery as ConceptMasteryData, MasteryLevel } from '../types';
import { fetchConceptMastery } from '../services/apiService';

const masterylevelColor = (level: MasteryLevel): string => {
  switch (level) {
    case 'Beginner': return 'bg-red-100 text-red-900 border-red-300';
    case 'Intermediate': return 'bg-yellow-100 text-yellow-900 border-yellow-300';
    case 'Advanced': return 'bg-green-100 text-green-900 border-green-300';
  }
};

const masteryLevelIcon = (level: MasteryLevel): string => {
  switch (level) {
    case 'Beginner': return '🌱';
    case 'Intermediate': return '🌿';
    case 'Advanced': return '🌳';
  }
};

interface ConceptMasteryItemProps {
  concept: ConceptMasteryData;
}

const ConceptMasteryItem: React.FC<ConceptMasteryItemProps> = ({ concept }) => {
  // Map theta to a visual bar width (0-100%)
  const barWidth = Math.max(0, Math.min(100, ((concept.theta + 3) / 6) * 100));

  return (
    <div className="p-4 bg-white border border-[#2D1B14]/10 rounded-lg hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="text-sm font-bold text-[#2D1B14]">{concept.concept}</h4>
          <p className="text-xs text-[#2D1B14]/50 mt-1">
            {concept.responses} {concept.responses === 1 ? 'response' : 'responses'}
          </p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${masterylevelColor(concept.level)}`}>
          {masteryLevelIcon(concept.level)} {concept.level}
        </span>
      </div>

      {/* Theta visualization bar */}
      <div className="mb-3">
        <div className="w-full h-2 bg-[#2D1B14]/5 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#D4AF37] transition-all duration-300"
            style={{ width: `${barWidth}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-[#2D1B14]/40 mt-1">
          <span>Weak</span>
          <span>θ = {concept.theta.toFixed(2)}</span>
          <span>Strong</span>
        </div>
      </div>

      <p className="text-[10px] text-[#2D1B14]/40">
        Last updated: {new Date(concept.lastUpdated).toLocaleDateString()}
      </p>
    </div>
  );
};

interface ConceptMasteryProps {
  isVisible?: boolean;
}

export const ConceptMastery: React.FC<ConceptMasteryProps> = ({ isVisible = true }) => {
  const [data, setData] = useState<ConceptBreakdown | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isVisible) return;

    const loadConceptMastery = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await fetchConceptMastery();
        setData(result);
      } catch (err: any) {
        setError(err.message || 'Failed to load concept mastery data');
      } finally {
        setIsLoading(false);
      }
    };

    loadConceptMastery();
  }, [isVisible]);

  if (!isVisible) return null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-12 text-[#D4AF37]">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-sm font-bold uppercase tracking-widest">Loading Concept Mastery...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 p-6 bg-red-50 border border-red-200 text-red-700 rounded-lg">
        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (!data?.concepts || Object.keys(data.concepts).length === 0) {
    return (
      <div className="p-8 bg-[#FDFCF7] border border-[#D4AF37]/20 rounded-lg text-center">
        <p className="text-[#2D1B14]/60 italic mb-2">No concepts tracked yet</p>
        <p className="text-xs text-[#2D1B14]/40">
          Start answering questions to build your concept mastery profile!
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-black font-playfair text-[#2D1B14] mb-2">Concept Mastery</h2>
        <p className="text-sm text-[#2D1B14]/60 italic">
          Track your expertise across specific knowledge domains. Continue answering questions to refine your profile.
        </p>
      </div>

      {(Object.entries(data.concepts) as [string, ConceptMasteryData[]][]).map(([topic, concepts]) => (
        <div key={topic} className="space-y-4">
          {/* Topic header */}
          <div className="flex items-center gap-3 pb-3 border-b border-[#D4AF37]/20">
            <h3 className="text-lg font-bold text-[#2D1B14]">{topic}</h3>
            <div className="text-xs font-bold text-[#D4AF37] uppercase tracking-widest">
              {concepts.length} {concepts.length === 1 ? 'Concept' : 'Concepts'}
            </div>
          </div>

          {/* Grid of concepts */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {concepts.map((concept) => (
              <ConceptMasteryItem key={`${topic}-${concept.concept}`} concept={concept} />
            ))}
          </div>

          {/* Topic level stats */}
          <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-[#2D1B14]/5">
            <div className="text-center p-4 bg-[#FDFCF7] rounded-lg">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">
                {(concepts as ConceptMasteryData[]).filter(c => c.level === 'Advanced').length}
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mt-1">Advanced</div>
            </div>
            <div className="text-center p-4 bg-[#FDFCF7] rounded-lg">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">
                {(concepts as ConceptMasteryData[]).filter(c => c.level === 'Intermediate').length}
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mt-1">Intermediate</div>
            </div>
            <div className="text-center p-4 bg-[#FDFCF7] rounded-lg">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">
                {(concepts as ConceptMasteryData[]).filter(c => c.level === 'Beginner').length}
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mt-1">Beginner</div>
            </div>
          </div>
        </div>
      ))}

      {/* Legend */}
      <div className="mt-8 p-6 bg-[#FDFCF7] border border-[#D4AF37]/20 rounded-lg">
        <h4 className="text-xs font-bold uppercase tracking-widest text-[#D4AF37] mb-3">Mastery Levels</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
            <div>
              <div className="text-sm font-bold text-[#2D1B14]">Advanced (θ ≥ 1.0)</div>
              <p className="text-xs text-[#2D1B14]/60">Expert in this domain</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
            <div>
              <div className="text-sm font-bold text-[#2D1B14]">Intermediate (-1.0 ≤ θ &lt; 1.0)</div>
              <p className="text-xs text-[#2D1B14]/60">Learning this domain</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-red-500"></div>
            <div>
              <div className="text-sm font-bold text-[#2D1B14]">Beginner (θ &lt; -1.0)</div>
              <p className="text-xs text-[#2D1B14]/60">Building foundation</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConceptMastery;
