export type OutgoingPlayerOption = {
  player_id: number;
  web_name: string;
  position: string;
  team_short_name: string;
};

export function OutgoingPlayerSelector({
  players,
  onSelect,
}: {
  players: OutgoingPlayerOption[];
  onSelect: (playerId: number) => void;
}): JSX.Element {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Who are you transferring out?</h2>
      <p className="mt-1 text-sm text-slate-600">
        Choose a player from your current squad to see ranked legal replacements.
      </p>
      <label className="mt-4 block max-w-sm text-sm text-slate-700">
        Outgoing player
        <select
          aria-label="Outgoing player"
          className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5"
          defaultValue=""
          onChange={(event) => {
            const value = Number(event.target.value);
            if (!Number.isNaN(value) && value > 0) {
              onSelect(value);
            }
          }}
        >
          <option value="" disabled>
            Select a player
          </option>
          {players.map((player) => (
            <option key={player.player_id} value={player.player_id}>
              {player.web_name} ({player.position} · {player.team_short_name})
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
