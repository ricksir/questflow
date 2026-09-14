import { Stack } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { StatusBar, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QuestFlowProvider } from '../src/context/QuestFlowContext';
import { palette } from '../src/components/ui';
import { suppressDevelopmentChrome } from '../src/lib/devUi';

suppressDevelopmentChrome();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <View style={{ flex: 1, backgroundColor: palette.bg }}>
        <QuestFlowProvider>
          <StatusBar barStyle="dark-content" backgroundColor={palette.bg} translucent={false} />
          <Stack screenOptions={{ headerStyle: { backgroundColor: palette.bg }, headerTintColor: palette.text, headerShadowVisible: false, contentStyle: { backgroundColor: palette.bg }, animation: 'fade' }}>
            <Stack.Screen name="index" options={{ headerShown: false }} />
            <Stack.Screen name="pair" options={{ title: 'Conectar ao QuestFlow' }} />
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          </Stack>
        </QuestFlowProvider>
      </View>
    </SafeAreaProvider>
  );
}
