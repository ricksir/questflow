import * as Crypto from 'expo-crypto';
import { Platform } from 'react-native';
import { MOBILE_APP_VERSION } from './config';
import type { LearningEvent } from './types';

let localSequence = 0;

export function createLearningEvent(input: Omit<LearningEvent, 'event_id' | 'schema_version' | 'occurred_at' | 'sequence_no' | 'client'>): LearningEvent {
  localSequence += 1;
  return {
    ...input,
    event_id: Crypto.randomUUID(),
    schema_version: 1,
    occurred_at: new Date().toISOString(),
    sequence_no: localSequence,
    client: {
      platform: Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : Platform.OS,
      version: MOBILE_APP_VERSION,
    },
  };
}
