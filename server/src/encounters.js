import { createHash } from 'node:crypto';

/** Only already validated, executable scenarios enter this local selection menu.
 * No APK unlock/loot behavior is inferred from the availability of a loader. */
export function createEncounterDirectory({ baseTutorial, current, cityPreview, customScenarioPath }) {
  if (!baseTutorial) return null;
  const entries = new Map();
  const add = (id, scenario, classification, source) => entries.set(id, {
    scenario: Object.freeze({ ...scenario, encounterId: id }),
    summary: { id, title: scenario.title, notice: scenario.notice, definitionId: scenario.definition.id,
      classification, source, player: { id: scenario.definition.player.id, name: scenario.definition.player.name },
      enemy: { id: scenario.definition.enemy.id, name: scenario.definition.enemy.name } },
  });
  add('tutorial-5000', baseTutorial, 'recovered-tutorial-with-reconstruction-rules', { challengeId: 3997, battleId: 5000 });
  let defaultEncounterId = 'tutorial-5000';
  if (cityPreview) {
    defaultEncounterId = 'city-preview-10405';
    add(defaultEncounterId, current, 'local-reconstruction-preview', { battleId: 10405 });
  } else if (customScenarioPath) {
    defaultEncounterId = 'custom';
    add(defaultEncounterId, current, 'custom-content', null);
  }
  const directory = { schemaVersion: 1, defaultEncounterId, selectionPolicy: 'explicit-local-selection',
    originalUnlockBehaviorVerified: false, rewardsImplemented: false,
    encounters: [...entries.values()].map(entry => entry.summary) };
  const contentId = createHash('sha256').update(JSON.stringify(directory)).digest('hex');
  return { directory: { ...directory, contentId }, resolve: id => entries.get(id)?.scenario ?? null };
}
