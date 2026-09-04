import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { createTimer, markInteraction, setForeground, setQuestionScreenActive, snapshotTimer, tickTimer, type TimerSnapshot, type TimerState } from './timing';

export function useActiveResponseTimer(questionKey: string, questionScreenFocused = true) {
  const stateRef = useRef<TimerState>(createTimer(Date.now()));
  const [live, setLive] = useState<TimerSnapshot>(() => snapshotTimer(stateRef.current, Date.now()));

  const reset = useCallback(() => {
    stateRef.current = createTimer(Date.now());
    stateRef.current = setQuestionScreenActive(stateRef.current, questionScreenFocused, Date.now());
    setLive(snapshotTimer(stateRef.current, Date.now()));
  }, [questionScreenFocused]);

  useEffect(() => { reset(); }, [questionKey, reset]);

  useEffect(() => {
    stateRef.current = setQuestionScreenActive(stateRef.current, questionScreenFocused, Date.now());
    setLive(snapshotTimer(stateRef.current, Date.now()));
  }, [questionScreenFocused]);

  useEffect(() => {
    const timer = setInterval(() => {
      stateRef.current = tickTimer(stateRef.current, Date.now());
      setLive(snapshotTimer(stateRef.current, Date.now()));
    }, 1000);
    const appState = AppState.addEventListener('change', (next) => {
      stateRef.current = setForeground(stateRef.current, next === 'active', Date.now());
      setLive(snapshotTimer(stateRef.current, Date.now()));
    });
    return () => {
      clearInterval(timer);
      appState.remove();
    };
  }, []);

  const interaction = useCallback(() => {
    stateRef.current = markInteraction(stateRef.current, Date.now());
    setLive(snapshotTimer(stateRef.current, Date.now()));
  }, []);

  const snapshot = useCallback((): TimerSnapshot => snapshotTimer(stateRef.current, Date.now()), []);

  return { interaction, snapshot, reset, live };
}
