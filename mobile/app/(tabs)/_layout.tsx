import { Tabs } from 'expo-router';
import { Platform, Text, View, type ColorValue } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { palette } from '../../src/components/ui';

const tabIcon = (symbol: string, color: ColorValue, focused: boolean) => (
  <View style={{
    width: 40,
    height: 36,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: focused ? palette.primary : 'transparent',
    borderWidth: focused ? 1 : 0,
    borderColor: focused ? palette.primary : 'transparent',
  }}>
    <Text style={{ color: focused ? '#080A0E' : color, fontSize: 17, fontWeight: '900' }}>{symbol}</Text>
  </View>
);

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  // Alguns aparelhos Android antigos reportam bottom=0 mesmo com navegação por 3 botões.
  // Um piso pequeno mantém os controles do QuestFlow acima da barra do sistema.
  const bottom = Math.max(insets.bottom, Platform.OS === 'android' ? 28 : 10);
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarStyle: {
        backgroundColor: palette.bgAlt,
        borderColor: palette.border,
        borderWidth: 1,
        height: 62 + bottom,
        paddingTop: 7,
        paddingBottom: bottom,
        paddingHorizontal: 7,
        marginHorizontal: 10,
        marginBottom: 8,
        borderRadius: 20,
        position: 'absolute',
        elevation: 12,
        shadowColor: '#000',
        shadowOpacity: 0.28,
        shadowRadius: 14,
        shadowOffset: { width: 0, height: -6 },
      },
      tabBarItemStyle: { minHeight: 52, paddingVertical: 2 },
      tabBarLabelStyle: { fontSize: 11, fontWeight: '800', marginTop: 1 },
      tabBarActiveTintColor: '#FFFFFF',
      tabBarInactiveTintColor: palette.muted,
      sceneStyle: { backgroundColor: palette.bg, paddingBottom: 72 + bottom },
    }}>
      <Tabs.Screen name="today" options={{ title: 'Hoje', tabBarIcon: ({ color, focused }) => tabIcon('⌂', color, focused) }} />
      <Tabs.Screen name="questions" options={{ title: 'Questões', tabBarIcon: ({ color, focused }) => tabIcon('✓', color, focused) }} />
      <Tabs.Screen name="progress" options={{ title: 'Progresso', tabBarIcon: ({ color, focused }) => tabIcon('↗', color, focused) }} />
      <Tabs.Screen name="profile" options={{ title: 'Perfil', tabBarIcon: ({ color, focused }) => tabIcon('●', color, focused) }} />
    </Tabs>
  );
}
