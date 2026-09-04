import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

export type ReminderRegistration = {
  ok: boolean;
  state: 'scheduled' | 'denied' | 'unavailable';
  message: string;
  hour?: number;
  minute?: number;
};

const REMINDER_MARKER = 'questflow-study-reminder';

export async function registerNativePush(hour = 19, minute = 0): Promise<ReminderRegistration> {

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('study-reminders', {
      name: 'Lembretes de estudo',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  const current = await Notifications.getPermissionsAsync();
  let status = current.status;
  if (status !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== 'granted') {
    return {
      ok: false,
      state: 'denied',
      message: 'A permissão não foi concedida. Você pode ativá-la depois nas configurações do Android.',
    };
  }

  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const previous = scheduled.filter((item) => item.content.data?.questflow_marker === REMINDER_MARKER);
  await Promise.all(previous.map((item) => Notifications.cancelScheduledNotificationAsync(item.identifier)));

  await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Hora de revisar no QuestFlow',
      body: 'Abra sua próxima sessão e mantenha o ritmo de estudo.',
      sound: 'default',
      data: { questflow_marker: REMINDER_MARKER, destination: 'today' },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour,
      minute,
      ...(Platform.OS === 'android' ? { channelId: 'study-reminders' } : {}),
    },
  });

  return {
    ok: true,
    state: 'scheduled',
    hour,
    minute,
    message: `Lembrete diário ativado para ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}. Ele funciona neste aparelho sem depender do Firebase ou do computador.`,
  };
}
