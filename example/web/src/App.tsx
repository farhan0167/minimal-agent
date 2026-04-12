import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { ChatPanel } from "./components/chat/ChatPanel";
import { WelcomeScreen } from "./components/chat/WelcomeScreen";
import { useSessions } from "./hooks/use-sessions";

export default function App() {
  const {
    sessions,
    activeSession,
    createSession,
    selectSession,
    removeSession,
  } = useSessions();

  return (
    <div className="flex h-screen bg-[hsl(var(--aui-background))]">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSession?.session_id ?? null}
        onSelect={selectSession}
        onDelete={removeSession}
        onCreate={createSession}
      />

      <main className="flex flex-col flex-1 min-w-0">
        <Header session={activeSession} />

        <div className="flex-1 overflow-hidden">
          {activeSession ? (
            <ChatPanel sessionId={activeSession.session_id} agentType={activeSession.agent_type} />
          ) : (
            <WelcomeScreen />
          )}
        </div>
      </main>
    </div>
  );
}
