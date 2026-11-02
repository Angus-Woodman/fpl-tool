"use client";

import { Fragment, useId, useMemo, useState } from "react";

import {
  clubsIn,
  defaultDirection,
  filtersAreActive,
  filterCandidates,
  fixtureWindow,
  groupFixtures,
  NO_FILTERS,
  parseMaxPrice,
  sortCandidates,
  statusesIn,
  type Filters,
  type GameweekFixtures,
  type SortDirection,
  type SortKey,
} from "@/components/transfers/planner/planner-candidate-view";
import {
  describePlayingStatus,
  playingStatusWarning,
} from "@/components/transfers/playing-status";
import { describePlannerReasons } from "@/components/transfers/planner/planner-reasons";
import {
  formatGameweekRanges,
  formatSignedPoints,
  formatTenths,
  horizonLabel,
} from "@/components/transfers/planner/planner-format";
import type {
  PlanExplorerCandidate,
  PlanExplorerHorizonInfo,
  PlanExplorerHorizonKey,
  TransferHorizon,
} from "@/lib/api";

const HORIZON_KEYS: PlanExplorerHorizonKey[] = ["1", "3", "5"];

// Below the md breakpoint each row stacks into a labelled card so the state
// and plan impact are never hidden behind sideways scrolling.
const CELL =
  "py-2 pr-3 max-md:flex max-md:items-start max-md:justify-between max-md:gap-4 max-md:py-1 max-md:pr-0 before:text-xs before:font-medium before:uppercase before:tracking-wide before:text-slate-500 before:content-[attr(data-label)] md:before:content-none";

function StateCell({
  candidate,
}: {
  candidate: PlanExplorerCandidate;
}): JSX.Element {
  if (candidate.state === "available") {
    return (
      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900">
        Available
      </span>
    );
  }
  if (candidate.state === "blocked_by_later_decision") {
    const conflict = candidate.conflict;
    if (conflict?.kind === "financial") {
      // The shortfall gameweek is shown only to explain the shortfall; it is not a valid gameweek.
      return (
        <div className="text-xs text-amber-900">
          <span className="rounded bg-amber-100 px-2 py-0.5 font-medium">
            {`Blocked from GW${conflict.gameweek}: short by ${formatTenths(conflict.shortfall_tenths)}`}
          </span>
          <p className="mt-1 text-slate-600">{conflict.message}</p>
          <p className="mt-1 text-slate-600">
            GW{conflict.gameweek} cannot be afforded; its figures only explain
            the shortfall.
          </p>
        </div>
      );
    }
    return (
      <div className="text-xs text-amber-900">
        <span className="rounded bg-amber-100 px-2 py-0.5 font-medium">
          {conflict
            ? `Blocked by GW${conflict.gameweek} planned transfer`
            : "Blocked by a later planned transfer"}
        </span>
        {conflict && <p className="mt-1 text-slate-600">{conflict.message}</p>}
        {candidate.valid_through_gameweek !== null && (
          <p className="mt-1 text-slate-600">
            Valid through GW{candidate.valid_through_gameweek}
          </p>
        )}
      </div>
    );
  }
  return (
    <span className="text-xs text-red-700">
      Unavailable: {describePlannerReasons(candidate.reasons).join("; ")}
    </span>
  );
}

function PlanImpactCell({
  candidate,
  horizon,
}: {
  candidate: PlanExplorerCandidate;
  horizon: TransferHorizon;
}): JSX.Element {
  const impact =
    candidate.plan_impact_by_horizon[String(horizon) as PlanExplorerHorizonKey];
  return (
    <div data-testid="plan-impact" className="space-y-0.5 text-xs">
      <p data-testid="impact-saved-plan">
        Saved plan: {formatSignedPoints(impact.saved_plan)}
      </p>
      <p data-testid="impact-assumed-continuation">
        Assumed continuation (no plan decisions):{" "}
        {formatSignedPoints(impact.assumed_continuation)}
      </p>
      <p data-testid="impact-net" className="text-slate-600">
        Saved plan after transfer hit:{" "}
        {formatSignedPoints(impact.net_saved_plan)}
      </p>
      {impact.valid_through_gameweek !== null &&
        (candidate.conflict?.kind === "financial" ? (
          <p className="text-slate-600">
            Includes GW{impact.valid_through_gameweek}, which cannot be afforded
          </p>
        ) : (
          <p className="text-slate-600">
            Valid through GW{impact.valid_through_gameweek}
          </p>
        ))}
    </div>
  );
}

function gainHeading(info: PlanExplorerHorizonInfo): string {
  return `Best-XI gain ${horizonLabel(info)}${info.partial ? " (partial)" : ""}`;
}

const SORT_LABELS: Record<Exclude<SortKey, "default">, string> = {
  "gain-1": "Best-XI gain over 1 GW",
  "gain-3": "Best-XI gain over 3 GWs",
  "gain-5": "Best-XI gain over 5 GWs",
  price: "Price",
  bank: "Resulting bank",
  difficulty: "Fixture difficulty",
};

function directionWords(key: SortKey, direction: SortDirection): string {
  if (key === "difficulty") {
    return direction === "asc" ? "easiest first" : "hardest first";
  }
  return direction === "asc" ? "lowest first" : "highest first";
}

const CONTROL =
  "min-h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-900";
const BUTTON =
  "inline-flex min-h-9 items-center justify-center rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-900 disabled:cursor-not-allowed disabled:opacity-50";

function Field({
  id,
  label,
  className = "",
  children,
}: {
  id: string;
  label: string;
  className?: string;
  children: JSX.Element;
}): JSX.Element {
  return (
    <div className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <label htmlFor={id} className="text-xs font-medium text-slate-700">
        {label}
      </label>
      {children}
    </div>
  );
}

function FixturesCell({ groups }: { groups: GameweekFixtures[] }): JSX.Element {
  return (
    <ul data-testid="fixtures" className="space-y-1 text-xs md:min-w-[11rem]">
      {groups.map((group) => {
        if (group.kind !== "fixtures") {
          const text = {
            blank: "Blank gameweek",
            missing: "No fixture data",
            not_evaluated: "Not evaluated",
          }[group.kind];
          return (
            <li
              key={group.gameweek}
              data-gameweek={group.gameweek}
              data-kind={group.kind}
              className="flex flex-wrap items-baseline gap-x-1 text-slate-500"
            >
              <span className="font-medium text-slate-700">
                GW{group.gameweek}
              </span>{" "}
              {text}
            </li>
          );
        }
        const double = group.fixtures.length > 1;
        return (
          <li
            key={group.gameweek}
            data-gameweek={group.gameweek}
            data-kind="fixtures"
            data-double={double ? "true" : undefined}
            className="flex flex-wrap items-baseline gap-x-1"
          >
            <span className="font-medium">GW{group.gameweek}</span>
            {double && (
              <>
                {" "}
                <span className="rounded bg-sky-100 px-1 text-sky-900">
                  Double
                </span>
              </>
            )}
            {group.fixtures.map((fixture, index) => (
              <Fragment key={index}>
                {" "}
                <span
                  data-testid="fixture"
                  className="inline-block whitespace-nowrap"
                >
                  {`${fixture.opponent_short_name} (${
                    fixture.is_home === null
                      ? "venue n/a"
                      : fixture.is_home
                        ? "H"
                        : "A"
                  })`}{" "}
                  <span className="rounded border border-slate-300 px-1 text-slate-700">
                    Diff {fixture.difficulty ?? "n/a"}
                  </span>
                </span>
              </Fragment>
            ))}
          </li>
        );
      })}
    </ul>
  );
}

type ActiveChip = { id: string; label: string; remove: () => void };

export function PlannerCandidateTable({
  candidates,
  horizons,
  horizon,
  bankIsEstimated,
  onPreview,
}: {
  candidates: PlanExplorerCandidate[];
  horizons: PlanExplorerHorizonInfo[];
  horizon: TransferHorizon;
  bankIsEstimated: boolean;
  onPreview: (playerId: number) => void;
}): JSX.Element {
  const ids = useId();
  const selectedInfo = horizons.find((info) => info.horizon === horizon);
  const impactHeading = `Plan impact${selectedInfo ? ` (${horizonLabel(selectedInfo)})` : ""}`;
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [chosenSort, setChosenSort] = useState<{
    key: SortKey;
    direction: SortDirection;
    horizon: TransferHorizon;
  }>({ key: "default", direction: "desc", horizon });
  // A new primary horizon is a new server ranking; show it rather than a stale local order.
  const sort =
    chosenSort.horizon === horizon
      ? chosenSort
      : {
          key: "default" as SortKey,
          direction: "desc" as SortDirection,
          horizon,
        };

  const gameweeks = useMemo(
    () => fixtureWindow(candidates, selectedInfo),
    [candidates, selectedInfo],
  );
  const clubs = useMemo(() => clubsIn(candidates), [candidates]);
  const statuses = useMemo(() => statusesIn(candidates), [candidates]);
  const maxPrice = parseMaxPrice(filters.maxPrice);
  const shown = useMemo(
    () =>
      sortCandidates(
        filterCandidates(candidates, filters),
        sort.key,
        sort.direction,
        { gameweeks, info: selectedInfo },
      ),
    [candidates, filters, sort.key, sort.direction, gameweeks, selectedInfo],
  );

  const update = (patch: Partial<Filters>) =>
    setFilters((current) => ({ ...current, ...patch }));
  const chooseSort = (key: SortKey) =>
    setChosenSort({ key, direction: defaultDirection(key), horizon });
  const sortActive = sort.key !== "default";
  const filtering = filtersAreActive(filters);

  const chips: ActiveChip[] = [];
  if (filters.search.trim() !== "") {
    chips.push({
      id: "search",
      label: `Search: "${filters.search.trim()}"`,
      remove: () => update({ search: "" }),
    });
  }
  if (filters.club !== "") {
    chips.push({
      id: "club",
      label: `Club: ${filters.club}`,
      remove: () => update({ club: "" }),
    });
  }
  if (maxPrice.kind === "ok") {
    chips.push({
      id: "price",
      label: `Maximum price: ${formatTenths(maxPrice.tenths)}`,
      remove: () => update({ maxPrice: "" }),
    });
  }
  if (filters.availableOnly) {
    chips.push({
      id: "available",
      label: "Available to apply only",
      remove: () => update({ availableOnly: false }),
    });
  }
  if (filters.status !== "") {
    chips.push({
      id: "status",
      label: `Playing status: ${describePlayingStatus(filters.status)}`,
      remove: () => update({ status: "" }),
    });
  }
  if (sortActive) {
    chips.push({
      id: "sort",
      label: `Sorted by ${SORT_LABELS[sort.key as Exclude<SortKey, "default">]}, ${directionWords(sort.key, sort.direction)}`,
      remove: () => chooseSort("default"),
    });
  }

  const ariaSort = (...keys: SortKey[]) =>
    sortActive && keys.includes(sort.key)
      ? sort.direction === "asc"
        ? ("ascending" as const)
        : ("descending" as const)
      : undefined;
  const windowLabel = formatGameweekRanges(gameweeks);
  const priceError = maxPrice.kind === "invalid";

  return (
    <div>
      <div
        role="group"
        aria-label="Search, filter and sort candidates"
        className="mb-3 grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 lg:grid-cols-4"
      >
        <Field
          id={`${ids}-search`}
          label="Search players"
          className="col-span-2"
        >
          <input
            id={`${ids}-search`}
            type="search"
            value={filters.search}
            onChange={(event) => update({ search: event.target.value })}
            placeholder="Name"
            autoComplete="off"
            className={CONTROL}
          />
        </Field>
        <Field id={`${ids}-club`} label="Club">
          <select
            id={`${ids}-club`}
            value={filters.club}
            onChange={(event) => update({ club: event.target.value })}
            className={CONTROL}
          >
            <option value="">All clubs</option>
            {clubs.map((club) => (
              <option key={club} value={club}>
                {club}
              </option>
            ))}
          </select>
        </Field>
        <Field id={`${ids}-price`} label="Maximum price (£m)">
          <input
            id={`${ids}-price`}
            type="text"
            inputMode="decimal"
            value={filters.maxPrice}
            onChange={(event) => update({ maxPrice: event.target.value })}
            placeholder="e.g. 6.5"
            autoComplete="off"
            aria-invalid={priceError ? true : undefined}
            aria-describedby={priceError ? `${ids}-price-error` : undefined}
            className={CONTROL}
          />
        </Field>
        <Field id={`${ids}-status`} label="Playing status">
          <select
            id={`${ids}-status`}
            value={filters.status}
            onChange={(event) => update({ status: event.target.value })}
            className={CONTROL}
          >
            <option value="">Any status</option>
            {statuses.map((code) => (
              <option key={code} value={code}>
                {describePlayingStatus(code)}
              </option>
            ))}
          </select>
        </Field>
        <div className="flex items-end">
          <label
            htmlFor={`${ids}-available`}
            className="flex min-h-9 items-center gap-2 text-sm text-slate-800"
          >
            <input
              id={`${ids}-available`}
              type="checkbox"
              checked={filters.availableOnly}
              onChange={(event) =>
                update({ availableOnly: event.target.checked })
              }
              className="h-4 w-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-900"
            />
            Available to apply only
          </label>
        </div>
        <Field id={`${ids}-sort`} label="Sort by" className="col-span-2">
          <div className="flex gap-2">
            <select
              id={`${ids}-sort`}
              value={sort.key}
              onChange={(event) => chooseSort(event.target.value as SortKey)}
              className={`${CONTROL} min-w-0 flex-1`}
            >
              <option value="default">Server ranking (default)</option>
              {(Object.keys(SORT_LABELS) as (keyof typeof SORT_LABELS)[]).map(
                (key) => (
                  <option key={key} value={key}>
                    {SORT_LABELS[key]}
                  </option>
                ),
              )}
            </select>
            <button
              type="button"
              disabled={!sortActive}
              aria-label={`Sort direction: ${directionWords(sort.key, sort.direction)}. Activate to reverse.`}
              onClick={() =>
                setChosenSort({
                  key: sort.key,
                  direction: sort.direction === "asc" ? "desc" : "asc",
                  horizon,
                })
              }
              className={BUTTON}
            >
              {sortActive ? (
                <>
                  <span aria-hidden="true" className="mr-1">
                    {sort.direction === "asc" ? "↑" : "↓"}
                  </span>
                  {directionWords(sort.key, sort.direction)}
                </>
              ) : (
                "Direction"
              )}
            </button>
          </div>
        </Field>
        {priceError && (
          <p
            id={`${ids}-price-error`}
            className="col-span-2 text-xs text-red-700 lg:col-span-4"
          >
            Enter a price in £m with at most one decimal place, for example 6.5.
          </p>
        )}
      </div>

      {chips.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <ul aria-label="Active filters" className="flex flex-wrap gap-2">
            {chips.map((chip) => (
              <li
                key={chip.id}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white pl-3 text-xs text-slate-800"
              >
                {chip.label}
                <button
                  type="button"
                  aria-label={`Remove ${chip.label}`}
                  onClick={chip.remove}
                  className="inline-flex min-h-8 min-w-8 items-center justify-center rounded-full hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-900"
                >
                  <span aria-hidden="true">×</span>
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              setFilters(NO_FILTERS);
              chooseSort("default");
            }}
            className="inline-flex min-h-8 items-center text-xs font-medium underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-900"
          >
            Reset filters and sort
          </button>
        </div>
      )}

      {sort.key === "difficulty" && (
        <p className="mb-2 text-xs text-slate-600">
          Ranked by the mean of the supplied difficulties over {windowLabel};
          blank gameweeks and missing values are ignored, and candidates with no
          difficulty come last.
        </p>
      )}
      <p
        data-testid="result-count"
        aria-live="polite"
        className="mb-2 text-xs text-slate-600"
      >
        Showing {shown.length} of {candidates.length} candidate
        {candidates.length === 1 ? "" : "s"}
      </p>

      {shown.length === 0 ? (
        <div
          data-testid="no-matches"
          className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-700"
        >
          <p>No candidates match these filters.</p>
          {filtering && (
            <button
              type="button"
              onClick={() => setFilters(NO_FILTERS)}
              className={`${BUTTON} mt-2`}
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <table
          aria-label="Replacement candidates"
          className="w-full border-collapse text-sm max-md:block"
        >
          <thead className="max-md:sr-only">
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-3">Player</th>
              <th className="py-2 pr-3">Team</th>
              <th className="py-2 pr-3" aria-sort={ariaSort("price")}>
                Price
              </th>
              <th className="py-2 pr-3" aria-sort={ariaSort("bank")}>
                Resulting bank
              </th>
              {horizons.map((info) => (
                <th
                  key={info.horizon}
                  className="py-2 pr-3"
                  aria-sort={ariaSort(`gain-${info.horizon}` as SortKey)}
                >
                  {gainHeading(info)}
                </th>
              ))}
              <th className="py-2 pr-3" aria-sort={ariaSort("difficulty")}>
                {windowLabel ? `Fixtures ${windowLabel}` : "Fixtures"}
              </th>
              <th className="py-2 pr-3">{impactHeading}</th>
              <th className="py-2 pr-3">State</th>
              <th className="py-2 pr-3">&nbsp;</th>
            </tr>
          </thead>
          <tbody className="max-md:block">
            {shown.map((candidate) => {
              const statusWarning = playingStatusWarning(candidate.status);
              return (
                <tr
                  key={candidate.player_id}
                  data-player-id={candidate.player_id}
                  data-state={candidate.state}
                  data-conflict={candidate.conflict?.kind}
                  className={`border-b border-slate-100 align-top max-md:flex max-md:flex-col max-md:py-3 ${
                    candidate.state === "available" ? "" : "bg-slate-50"
                  }`}
                >
                  <td className="py-2 pr-3 font-medium text-slate-900 max-md:order-1 max-md:py-1 max-md:text-base">
                    {candidate.web_name}
                    {statusWarning && (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-900">
                        {statusWarning}
                      </span>
                    )}
                  </td>
                  <td className={`${CELL} max-md:order-3`} data-label="Team">
                    {candidate.team_short_name}
                  </td>
                  <td className={`${CELL} max-md:order-3`} data-label="Price">
                    {formatTenths(candidate.price_tenths)}
                  </td>
                  <td
                    className={`${CELL} max-md:order-3`}
                    data-label="Resulting bank"
                  >
                    <span>
                      {formatTenths(candidate.resulting_bank_tenths)}
                      {bankIsEstimated &&
                        candidate.resulting_bank_tenths !== null && (
                          <span className="ml-1 text-xs text-slate-500">
                            Estimated
                          </span>
                        )}
                      {candidate.points_hit_after !== null &&
                        candidate.points_hit_after > 0 && (
                          <span className="block text-xs text-slate-600">
                            Hit after: -{candidate.points_hit_after} pts
                          </span>
                        )}
                    </span>
                  </td>
                  {HORIZON_KEYS.map((key) => {
                    const info = horizons.find(
                      (item) => String(item.horizon) === key,
                    );
                    return (
                      <td
                        key={key}
                        data-label={
                          info ? gainHeading(info) : `Best-XI gain ${key} GW`
                        }
                        className={`${CELL} max-md:order-3 ${
                          key === String(horizon) ? "font-semibold" : ""
                        }`}
                      >
                        {formatSignedPoints(
                          candidate.best_xi_gain_by_horizon[key] ?? null,
                        )}
                      </td>
                    );
                  })}
                  <td
                    className={`${CELL} max-md:order-3`}
                    data-label={
                      windowLabel ? `Fixtures ${windowLabel}` : "Fixtures"
                    }
                  >
                    <FixturesCell
                      groups={groupFixtures(candidate, gameweeks, selectedInfo)}
                    />
                  </td>
                  <td
                    className={`${CELL} max-md:order-3`}
                    data-label={impactHeading}
                  >
                    <PlanImpactCell candidate={candidate} horizon={horizon} />
                  </td>
                  <td className={`${CELL} max-md:order-2`} data-label="State">
                    <StateCell candidate={candidate} />
                  </td>
                  <td className={`${CELL} max-md:order-4`}>
                    <button
                      type="button"
                      onClick={() => onPreview(candidate.player_id)}
                      aria-label={`Preview ${candidate.web_name}`}
                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      Preview
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Best-XI gain compares the saved squad with the swap for the evaluated
        gameweeks. Preview a candidate to see its full effect before adding it.
        Fixtures show the opponent (H home, A away) and the difficulty the
        server supplied. Search, filters and sorting only re-order the
        server&apos;s results.
      </p>
    </div>
  );
}
