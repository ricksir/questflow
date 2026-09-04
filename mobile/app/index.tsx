import { Redirect } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';
import { useQuestFlow } from '../src/context/QuestFlowContext';
import { palette } from '../src/components/ui';

export default function Index() {
  const { loading, session } = useQuestFlow();
  if (loading) return <View style={{ flex: 1, backgroundColor: palette.bg, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator color={palette.primary} /></View>;
  return <Redirect href={session ? '/(tabs)/today' : '/pair'} />;
}
