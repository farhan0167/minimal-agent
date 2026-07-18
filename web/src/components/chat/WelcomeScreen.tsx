import { MessageSquare } from "lucide-react";
import { Text } from "../ui/Text";

export function WelcomeScreen() {
  return (
    <div className="chat-welcome flex flex-col items-center justify-center h-full text-center bg-app-bg">
      <MessageSquare className="w-12 h-12 text-app-accent/25 mb-4" />
      <Text variant="prose" as="h2" className="text-lg font-medium mb-2">
        No session selected
      </Text>
      <Text variant="prose" muted className="text-sm max-w-sm">
        Create a new session or select an existing one from the sidebar to start
        chatting with the agent.
      </Text>
    </div>
  );
}
