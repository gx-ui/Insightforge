export type SlashCommand = {
  name: string;
  description: string;
};

export type SlashCommandMatch = SlashCommand & {
  matchedPrefix: string;
  unmatchedSuffix: string;
};

export const SLASH_COMMANDS: SlashCommand[] = [
  {name: '/compact', description: '压缩当前会话上下文'},
];

export function matchingSlashCommands(input: string): SlashCommandMatch[] {
  if (!input.startsWith('/')) return [];
  const query = slashCommandQuery(input);
  return SLASH_COMMANDS
    .filter((command) => command.name.toLowerCase().startsWith(query.toLowerCase()))
    .map((command) => ({
      ...command,
      matchedPrefix: command.name.slice(0, query.length),
      unmatchedSuffix: command.name.slice(query.length),
    }));
}

export function slashCommandQuery(input: string): string {
  return input.trimStart().split(/\s+/, 1)[0] ?? '';
}

export function shouldShowSlashCommands(input: string, busy: boolean): boolean {
  return !busy && input.startsWith('/');
}
