import React from "react";
import {
  getPlanStepStatus,
  getPlanStepStatusClass,
  PLAN_STEP_STATUS,
} from "../utils/planStepStatus";

function StepStatusIcon({ status }) {
  if (status === PLAN_STEP_STATUS.COMPLETED) {
    return (
      <span className="w-5 h-5 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center">
        ✓
      </span>
    );
  }
  if (status === PLAN_STEP_STATUS.RUNNING) {
    return <span className="w-5 h-5 rounded-full bg-blue-500 animate-pulse" />;
  }
  if (status === PLAN_STEP_STATUS.FAILED) {
    return (
      <span className="w-5 h-5 rounded-full bg-rose-500 text-white text-[10px] flex items-center justify-center">
        !
      </span>
    );
  }
  return <span className="w-5 h-5 rounded-full border-2 border-slate-300" />;
}

export function InvestigationPlanPanel({
  currentPlan,
  isStreaming = false,
  status,
}) {
  const steps = currentPlan?.steps ?? [];

  if (steps.length === 0) {
    return null;
  }

  const stepCursor = currentPlan?.step_cursor ?? 0;

  return (
    <div className="border-b border-slate-100 bg-slate-50/50 px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Investigation Plan
        </h3>
        {currentPlan?.profile && (
          <span className="text-[10px] font-medium text-slate-400 uppercase">
            {currentPlan.profile.replace(/_/g, " ")}
          </span>
        )}
      </div>
      <div className="space-y-2 max-h-40 overflow-y-auto">
        {steps.map((step, index) => {
          const stepStatus = getPlanStepStatus(index, stepCursor, {
            isStreaming,
            status,
          });

          return (
            <div
              key={step.step_id ?? index}
              className={`rounded-xl border px-3 py-2 ${getPlanStepStatusClass(stepStatus)}`}
            >
              <div className="flex items-start gap-2">
                <StepStatusIcon status={stepStatus} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold truncate">
                    {step.tool_name}
                  </p>
                  <p className="text-[11px] mt-0.5 opacity-90 line-clamp-2">
                    {step.rationale}
                  </p>
                  {step.expected_evidence && (
                    <p className="text-[10px] mt-1 opacity-75">
                      Evidence: {step.expected_evidence}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
