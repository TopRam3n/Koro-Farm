import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { useToast } from '@/hooks/use-toast';

export interface Prediction {
  time: string;
  occupancy: number;
  energy: number;
  confidence: number;
}

export interface Suggestion {
  id: string;
  type: 'optimization' | 'warning' | 'insight';
  priority: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  potentialSavings?: string;
  affectedRooms: string[];
}

export interface PeakAlert {
  message: string;
  recommendation: string;
}

interface MLResponse {
  predictions: Prediction[];
  suggestions: Suggestion[];
  peakAlert?: PeakAlert | null;
}

export function usePredictions() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [peakAlert, setPeakAlert] = useState<PeakAlert | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const { toast } = useToast();

  const fetchPredictions = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data, error } = await supabase.functions.invoke<MLResponse>('ml-predictions', {
        method: 'POST',
      });

      if (error) throw error;

      if (data) {
        setPredictions(data.predictions || []);
        setSuggestions(
          (data.suggestions || []).map((s, i) => ({
            ...s,
            id: s.id || `suggestion-${i}`,
            affectedRooms: s.affectedRooms || [],
          }))
        );
        setPeakAlert(data.peakAlert || null);
        setLastUpdated(new Date());
      }
    } catch (error: any) {
      console.error('Failed to fetch predictions:', error);
      
      // Handle specific errors
      if (error.message?.includes('Rate limits exceeded')) {
        toast({
          title: "Rate limit reached",
          description: "Please wait a moment before refreshing predictions.",
          variant: "destructive",
        });
      } else if (error.message?.includes('Payment required')) {
        toast({
          title: "AI credits depleted",
          description: "Please add funds to continue using AI predictions.",
          variant: "destructive",
        });
      } else {
        // Use fallback predictions on error
        const hour = new Date().getHours();
        setPredictions(generateFallbackPredictions(hour));
      }
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  // Also fetch from database for stored suggestions
  const fetchStoredSuggestions = useCallback(async () => {
    try {
      const { data, error } = await supabase
        .from('ai_suggestions')
        .select('*')
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(5);

      if (error) throw error;

      if (data && data.length > 0) {
        setSuggestions(
          data.map(s => ({
            id: s.id,
            type: s.type as Suggestion['type'],
            priority: s.priority as Suggestion['priority'],
            title: s.title,
            description: s.description,
            potentialSavings: s.potential_savings || undefined,
            affectedRooms: [], // Would need to map room IDs to codes
          }))
        );
      }
    } catch (error) {
      console.error('Failed to fetch stored suggestions:', error);
    }
  }, []);

  useEffect(() => {
    fetchStoredSuggestions();

    // Subscribe to real-time suggestion updates
    const channel = supabase
      .channel('suggestions-updates')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'ai_suggestions',
        },
        () => {
          fetchStoredSuggestions();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetchStoredSuggestions]);

  return {
    predictions,
    suggestions,
    peakAlert,
    isLoading,
    lastUpdated,
    fetchPredictions,
    refresh: fetchPredictions,
  };
}

function generateFallbackPredictions(currentHour: number): Prediction[] {
  const predictions: Prediction[] = [];
  for (let i = 1; i <= 4; i++) {
    const hour = (currentHour + i) % 24;
    const period = hour >= 12 ? "PM" : "AM";
    const displayHour = hour > 12 ? hour - 12 : (hour === 0 ? 12 : hour);
    
    let occupancy: number, energy: number;
    if (hour >= 9 && hour <= 11) {
      occupancy = 80 + Math.floor(Math.random() * 15);
      energy = 75 + Math.floor(Math.random() * 20);
    } else if (hour >= 12 && hour <= 14) {
      occupancy = 60 + Math.floor(Math.random() * 20);
      energy = 65 + Math.floor(Math.random() * 15);
    } else if (hour >= 15 && hour <= 17) {
      occupancy = 50 + Math.floor(Math.random() * 25);
      energy = 55 + Math.floor(Math.random() * 20);
    } else {
      occupancy = 20 + Math.floor(Math.random() * 30);
      energy = 30 + Math.floor(Math.random() * 25);
    }
    
    predictions.push({
      time: `${displayHour}:00 ${period}`,
      occupancy,
      energy,
      confidence: 90 - i * 3
    });
  }
  return predictions;
}
