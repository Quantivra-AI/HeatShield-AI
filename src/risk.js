export const limits = {
  Light: { unacclimatized: 28, acclimatized: 30 },
  Moderate: { unacclimatized: 25, acclimatized: 28 },
  Heavy: { unacclimatized: 23, acclimatized: 26 },
  'Very heavy': { unacclimatized: 21, acclimatized: 25 },
}

export function assessRisk({ wbgt, workload, acclimatized, exposureHours, clothingAdjustment = 0 }) {
  const effective = Number(wbgt) + Number(clothingAdjustment)
  const limit = limits[workload][acclimatized ? 'acclimatized' : 'unacclimatized']
  let level, title, description, actions
  if (effective < limit - 2) {
    level = 'lower'; title = 'Within reference limit'
    description = 'The entered effective WBGT is below the applicable reference limit. Keep routine controls in place.'
    actions = ['Keep cool drinking water readily available.', 'Provide shaded or cooled recovery areas.', 'Recheck conditions when weather, workload or clothing changes.']
  } else if (effective < limit) {
    level = 'watch'; title = 'Approaching reference limit'
    description = 'Conditions are approaching the applicable reference limit. Increase monitoring and prepare additional controls.'
    actions = ['Increase the frequency of WBGT checks.', 'Plan shaded recovery breaks and reduce avoidable exertion.', 'Check acclimatization and the additional heat burden from PPE.']
  } else {
    level = 'high'; title = 'Reference limit exceeded'
    description = 'The entered effective WBGT meets or exceeds the applicable reference limit. Stronger controls are needed.'
    actions = ['Pause or modify strenuous work until controls are in place.', 'Move work to cooler hours where feasible.', 'Increase shaded or cooled rest breaks and supervisor check-ins.', 'Consult a qualified occupational-safety professional for work/rest planning.']
  }
  return { effective, limit, level, title, description, actions, exposureHours }
}
