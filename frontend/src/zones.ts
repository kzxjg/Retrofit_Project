// A zone question's option text starts with the zone name, for example
// "Zone 7A: Prairies and colder parts of central Canada (...)".
// The map identifies the same zone by its id, "zone7a".

export function zoneIdFromOption(option: string | undefined): string | null {
  if (!option) return null
  const name = option.split(':')[0].trim().toLowerCase().replace(/\s+/g, '')
  return /^zone\w+$/.test(name) ? name : null
}

export function optionForZoneId(options: string[], zoneId: string): string | undefined {
  return options.find((option) => zoneIdFromOption(option) === zoneId)
}
