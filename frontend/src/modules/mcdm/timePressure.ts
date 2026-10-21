export const TIME_PRESSURE_CUTOFF = "2026-01";

export function hasTimePressure(month: string): boolean {
  return month < TIME_PRESSURE_CUTOFF;
}

export function formatTimePressure(month: string, pressure: number): string {
  return hasTimePressure(month) ? pressure.toFixed(3) : "无";
}
