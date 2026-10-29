import type { ReactNode } from "react";

import { describePlannerReasons } from "@/components/transfers/planner/planner-reasons";
import {
  formatSignedPoints,
  formatTenths,
  horizonLabel,
} from "@/components/transfers/planner/planner-format";
import type {
  PlanExplorerHorizonKey,
  PlanPreviewGameweek,
  PlanTransferPreviewResponse,
  TransferHorizon,
} from "@/lib/api";

const HORIZON_KEYS: PlanExplorerHorizonKey[] = ["1", "3", "5"];

// Below the md breakpoint each row stacks into labelled lines so no figure sits behind sideways scrolling.
const CELL =
  "py-2 pr-3 max-md:flex max-md:justify-between max-md:gap-4 max-md:py-1 max-md:pr-0 before:text-xs before:font-medium before:uppercase before:tracking-wide before:text-slate-500 before:content-[attr(data-label)] md:before:content-none";
const ROW_HEADER =
  "py-2 pr-3 text-left font-medium max-md:block max-md:py-1 max-md:text-base";

const ROLE_LABELS: Record<
  NonNullable<PlanPreviewGameweek["incoming_role"]>,
  string
> = {
  starting: "Starting",
  bench: "Bench",
  captain: "Captain",
  vice_captain: "Vice-captain",
};

function formatHit(hit: number | null): string {
  if (hit === null) return "-";
  return hit > 0 ? `-${hit}` : "0";
}

function unavailableReason(week: PlanPreviewGameweek): string {
  switch (week.reason) {
    case "financial_shortfall":
      return `Not valid: short by ${formatTenths(week.shortfall_tenths)}`;
    case "beyond_valid_range":
      return "Not valid: after the last gameweek this transfer can be applied";
    case "continuation_lineup_illegal":
      return "Not valid: the continued squad has no legal lineup";
    case "no_projection":
      return "Not valid: no projection for this gameweek";
    default:
      return "Not valid";
  }
}

function GameweekRow({ week }: { week: PlanPreviewGameweek }): JSX.Element {
  const accounting = week.accounting;
  // The server keeps points and roles for a financially invalid gameweek; show what it returned, labelled.
  const hasFigures = week.points !== null || week.incoming_role !== null;
  return (
    <tr
      data-testid={`preview-gw-${week.gameweek}`}
      data-gameweek={week.gameweek}
      data-basis={week.basis}
      data-valid={String(week.valid)}
      className={`border-b border-slate-100 align-top max-md:flex max-md:flex-col max-md:py-3 ${
        week.valid ? "" : "bg-amber-50 italic text-slate-600"
      }`}
    >
      <th scope="row" className={ROW_HEADER}>
        GW{week.gameweek}
        {week.chip && (
          <span className="ml-1 text-xs font-normal text-slate-500">
            {week.chip}
          </span>
        )}
      </th>
      <td className={CELL} data-label="Bank before → after">
        {accounting
          ? `${formatTenths(accounting.before.closing_bank_tenths)} → ${formatTenths(accounting.after.closing_bank_tenths)}`
          : "-"}
      </td>
      <td className={CELL} data-label="Free transfers after">
        {accounting ? (accounting.after.free_transfers_available ?? "-") : "-"}
      </td>
      <td className={CELL} data-label="Hit before → after">
        {accounting
          ? `${formatHit(accounting.before.points_hit)} → ${formatHit(accounting.after.points_hit)}`
          : "-"}
      </td>
      <td className={CELL} data-label="Incoming player">
        {week.incoming_role
          ? ROLE_LABELS[week.incoming_role]
          : week.valid
            ? "Not in squad"
            : "-"}
      </td>
      <td className={CELL} data-label="Points before → after">
        {week.points
          ? `${week.points.before.toFixed(1)} → ${week.points.after.toFixed(1)}`
          : "-"}
      </td>
      <td className={`${CELL} font-medium`} data-label="Change (before hits)">
        {week.points ? formatSignedPoints(week.points.delta) : "-"}
      </td>
      <td className="py-2 text-xs text-amber-900 max-md:py-1">
        {week.valid
          ? ""
          : hasFigures
            ? `Invalid scenario. ${unavailableReason(week)}. Figures are shown only to explain it.`
            : unavailableReason(week)}
      </td>
    </tr>
  );
}

function GameweekTable({
  weeks,
}: {
  weeks: PlanPreviewGameweek[];
}): JSX.Element {
  return (
    <div>
      <table className="w-full border-collapse text-sm max-md:block">
        <thead className="max-md:sr-only">
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3">Gameweek</th>
            <th className="py-2 pr-3">Bank before → after</th>
            <th className="py-2 pr-3">Free transfers after</th>
            <th className="py-2 pr-3">Hit before → after</th>
            <th className="py-2 pr-3">Incoming player</th>
            <th className="py-2 pr-3">Points before → after</th>
            <th className="py-2 pr-3">Change (before hits)</th>
            <th className="py-2">Note</th>
          </tr>
        </thead>
        <tbody className="max-md:block">
          {weeks.map((week) => (
            <GameweekRow key={week.gameweek} week={week} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConflictNote({
  data,
}: {
  data: PlanTransferPreviewResponse;
}): JSX.Element | null {
  const conflict = data.conflict;
  if (data.state === "unavailable") {
    return (
      <p
        data-testid="preview-state"
        className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
      >
        Unavailable: {describePlannerReasons(data.reasons).join("; ")}
      </p>
    );
  }
  if (!conflict) return null;
  if (conflict.kind === "financial") {
    const shortfall =
      conflict.shortfall_tenths ??
      data.gameweeks.find((week) => week.gameweek === conflict.gameweek)
        ?.shortfall_tenths ??
      null;
    return (
      <p
        data-testid="preview-conflict"
        className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
      >
        GW{conflict.gameweek} would overdraw the bank
        {shortfall !== null && ` by ${formatTenths(shortfall)}`}.{" "}
        {conflict.message} Its figures below only explain the shortfall; it is
        not a valid gameweek.
      </p>
    );
  }
  return (
    <p
      data-testid="preview-conflict"
      className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
    >
      Blocked by GW{conflict.gameweek}: {conflict.message}
      {data.valid_through_gameweek !== null &&
        ` Figures are shown only through GW${data.valid_through_gameweek}.`}{" "}
      Nothing else in your plan is changed to make room for this transfer.
    </p>
  );
}

function Totals({
  data,
  horizon,
}: {
  data: PlanTransferPreviewResponse;
  horizon: TransferHorizon;
}): JSX.Element {
  return (
    <section aria-label="Totals by horizon">
      <table className="w-full border-collapse text-sm max-md:block">
        <thead className="max-md:sr-only">
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3">Horizon</th>
            <th className="py-2 pr-3">Saved plan</th>
            <th className="py-2 pr-3">
              Assumed continuation (no plan decisions)
            </th>
            <th className="py-2 pr-3">Hit change</th>
            <th className="py-2">Saved plan after hit</th>
          </tr>
        </thead>
        <tbody className="max-md:block">
          {HORIZON_KEYS.map((key) => {
            const totals = data.totals[key];
            const info = data.projection.horizons.find(
              (item) => String(item.horizon) === key,
            );
            return (
              <tr
                key={key}
                data-testid={`totals-${key}`}
                aria-current={key === String(horizon) ? "true" : undefined}
                className={`border-b border-slate-100 max-md:flex max-md:flex-col max-md:py-3 ${
                  key === String(horizon) ? "font-semibold" : ""
                }`}
              >
                <th scope="row" className={ROW_HEADER}>
                  {key} GW{key === "1" ? "" : "s"}
                  {info &&
                    ` · ${horizonLabel(info)}${info.partial ? " (partial)" : ""}`}
                </th>
                <td className={CELL} data-label="Saved plan">
                  {formatSignedPoints(totals.saved_plan)}
                </td>
                <td
                  className={CELL}
                  data-label="Assumed continuation (no plan decisions)"
                >
                  {formatSignedPoints(totals.assumed_continuation)}
                </td>
                <td className={CELL} data-label="Hit change">
                  {totals.hit_change}
                </td>
                <td className={CELL} data-label="Saved plan after hit">
                  {formatSignedPoints(totals.net_saved_plan)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function PlannerTransferPreview({
  data,
  gameweek,
  horizon,
  onClose,
  children,
}: {
  data: PlanTransferPreviewResponse;
  gameweek: number;
  horizon: TransferHorizon;
  onClose: () => void;
  children: ReactNode;
}): JSX.Element {
  const saved = data.gameweeks.filter((week) => week.basis === "saved_plan");
  const assumed = data.gameweeks.filter(
    (week) => week.basis === "assumed_continuation",
  );
  const effect = data.lineup_effect;
  return (
    <section
      aria-label="Transfer preview"
      className="space-y-4 rounded-xl border border-slate-300 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900">
          Preview: {data.outgoing.web_name} for {data.candidate.web_name} in GW
          {gameweek}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          Close preview
        </button>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Incoming price</dt>
          <dd>{formatTenths(data.candidate.price_tenths)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Outgoing market price</dt>
          <dd>{formatTenths(data.outgoing.market_price_tenths)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Plan revision</dt>
          <dd>{data.planning_context.revision}</dd>
        </div>
      </dl>
      <ConflictNote data={data} />
      <section aria-label="Saved plan gameweeks" className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">Saved plan</h3>
        <GameweekTable weeks={saved} />
      </section>
      {assumed.length > 0 && (
        <section
          aria-label="Assumed continuation (no plan decisions)"
          className="space-y-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3"
        >
          <h3 className="text-sm font-semibold text-slate-900">
            Assumed continuation (no plan decisions)
          </h3>
          <p className="text-xs text-slate-600">
            These gameweeks come after the plan ends. They assume the squad
            stays as it is with no further decisions, and are never added to the
            saved plan figures.
          </p>
          <GameweekTable weeks={assumed} />
        </section>
      )}
      <Totals data={data} horizon={horizon} />
      <p data-testid="lineup-effect" className="text-sm text-slate-700">
        {effect.captain_changed || effect.vice_captain_changed
          ? `This transfer changes the ${[
              effect.captain_changed ? "captain" : null,
              effect.vice_captain_changed ? "vice-captain" : null,
            ]
              .filter(Boolean)
              .join(" and ")} in the evaluated gameweeks.`
          : "This transfer does not change the captain or vice-captain."}
      </p>
      {children}
    </section>
  );
}

export type CommitRegionModel =
  | { kind: "ready"; revision: number; onConfirm: () => void }
  | { kind: "disabled"; reason: string; onPreviewAgain?: () => void }
  | { kind: "saving"; reason: string }
  | {
      kind: "unknown";
      message: string | null;
      onCheck: () => void;
      onRetry: () => void;
    }
  | {
      kind: "pending_unsaved";
      onCheck: () => void;
      onRetry: () => void;
      onStop: () => void;
    }
  | { kind: "conflict"; message: string | null; onRefresh: () => void };

const BUTTON =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

export function PlannerCommitRegion({
  gameweek,
  model,
  standalone = false,
  label = null,
}: {
  gameweek: number;
  model: CommitRegionModel;
  /** An unresolved submission, shown apart from any candidate preview. */
  standalone?: boolean;
  /** Names the submission a standalone region belongs to. */
  label?: string | null;
}): JSX.Element {
  const title = standalone
    ? "Unresolved transfer confirmation"
    : `Add to plan GW${gameweek}`;
  let content: JSX.Element;
  switch (model.kind) {
    case "ready":
      content = (
        <>
          <p className="text-sm text-slate-700">
            Confirming adds this transfer to GW{gameweek} of your plan, which is
            currently at revision {model.revision}.
          </p>
          <button
            type="button"
            onClick={model.onConfirm}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            Confirm transfer
          </button>
        </>
      );
      break;
    case "disabled":
      content = (
        <>
          <button type="button" disabled className={BUTTON}>
            Confirm transfer
          </button>
          <p
            data-testid="confirm-disabled-reason"
            className="text-sm text-slate-700"
          >
            {model.reason}
          </p>
          {model.onPreviewAgain && (
            <button
              type="button"
              onClick={model.onPreviewAgain}
              className={BUTTON}
            >
              Preview again
            </button>
          )}
        </>
      );
      break;
    case "saving":
      content = (
        <>
          <p role="status" aria-label="Saving transfer" className="text-sm">
            Saving this transfer to your plan...
          </p>
          {!standalone && (
            <>
              <button type="button" disabled className={BUTTON}>
                Confirm transfer
              </button>
              <p
                data-testid="confirm-disabled-reason"
                className="text-sm text-slate-700"
              >
                {model.reason}
              </p>
            </>
          )}
        </>
      );
      break;
    case "unknown":
      content = (
        <div
          role="alert"
          data-testid="commit-unknown"
          className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <p className="font-medium">
            We could not confirm whether the server received this transfer.
          </p>
          {model.message && <p>{model.message}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={model.onCheck} className={BUTTON}>
              Check save status
            </button>
            <button type="button" onClick={model.onRetry} className={BUTTON}>
              Retry same transfer
            </button>
          </div>
        </div>
      );
      break;
    case "pending_unsaved":
      content = (
        <div
          role="alert"
          data-testid="commit-pending"
          className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <p className="font-medium">
            The server accepted this transfer but has not saved it to your plan
            yet.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={model.onRetry} className={BUTTON}>
              Retry same transfer
            </button>
            <button type="button" onClick={model.onCheck} className={BUTTON}>
              Check save status
            </button>
          </div>
          <div className="space-y-2 border-t border-red-200 pt-2">
            <p>
              The server accepted this transfer but could not save it. If you
              stop tracking it, it will not be added to your plan and this app
              will not retry it. The server may keep a pending record of it,
              which is not a saved transfer.
            </p>
            <button type="button" onClick={model.onStop} className={BUTTON}>
              Stop tracking this transfer
            </button>
          </div>
        </div>
      );
      break;
    case "conflict":
      content = (
        <div
          role="alert"
          data-testid="commit-conflict"
          className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <p className="font-medium">
            The plan changed on the server, so this transfer was not submitted
            against the newer version.
          </p>
          {model.message && <p>{model.message}</p>}
          <button type="button" onClick={model.onRefresh} className={BUTTON}>
            Refresh and preview again
          </button>
        </div>
      );
      break;
  }
  return (
    <section
      aria-label={title}
      className="space-y-3 border-t border-slate-200 pt-4"
    >
      <h3 className="text-sm font-semibold text-slate-900">
        {standalone
          ? `Unresolved transfer: ${label ?? "an earlier transfer"}`
          : title}
      </h3>
      {content}
    </section>
  );
}
