import { MessageSquare } from "lucide-react";

export function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center bg-[hsl(var(--aui-background))]">
      <MessageSquare className="w-12 h-12 text-[hsl(var(--aui-primary)/0.25)] mb-4" />
      <h2 className="text-lg font-medium text-[hsl(var(--aui-foreground))] mb-2 font-serif">
        No session selected
      </h2>
      <p className="text-sm text-[hsl(var(--aui-muted-foreground))] max-w-sm font-serif">
        Create a new session or select an existing one from the sidebar to start
        chatting with the agent.
      </p>
    </div>
  );
}
