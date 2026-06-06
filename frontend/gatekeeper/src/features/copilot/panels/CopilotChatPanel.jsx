import React from "react";
import {
  MessageList,
  StreamingIndicator,
  QuestionInput,
} from "../chat";

export function CopilotChatPanel({
  messages,
  isStreaming,
  isAwaitingApproval,
  isLoading,
  onAsk,
  approvalSlot,
}) {
  const inputDisabled = isLoading || isStreaming || isAwaitingApproval;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <MessageList messages={messages} />
      <StreamingIndicator isStreaming={isStreaming} />
      {approvalSlot}
      <QuestionInput onSubmit={onAsk} disabled={inputDisabled} />
    </div>
  );
}
