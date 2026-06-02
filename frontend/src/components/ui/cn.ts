/**
 * Tiny classname joiner. Filters out falsy values so conditional classes can be
 * written inline without pulling in a dependency.
 */
export type ClassValue = string | number | false | null | undefined;

export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(' ');
}
