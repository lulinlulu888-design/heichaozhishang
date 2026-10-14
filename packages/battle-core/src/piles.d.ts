export type PileZone = 'hand' | 'draw' | 'discard' | 'exhausted' | 'powerUsed' | 'removed';
export type PileState = Readonly<Record<PileZone, readonly string[]>>;
export type RoundDestination = 'hand' | 'discard' | 'exhausted' | 'removed';
export type PlayedDestination = Exclude<PileZone, 'hand'>;
export type PileEvent =
  | Readonly<{ type: 'DiscardRecycled'; cardIds: readonly string[] }>
  | Readonly<{ type: 'CardDrawn'; cardId: string }>
  | Readonly<{ type: 'PlayedCardMoved'; cardId: string; destination: PlayedDestination; drawIndex?: number }>
  | Readonly<{ type: 'CardRetained' | 'RoundEndCardMoved'; cardId: string; destination: RoundDestination }>;
export interface PileResult { readonly piles: PileState; readonly events: readonly PileEvent[] }
export declare function createPiles(state: PileState): PileState;
export declare function drawCards(state: PileState, count: number,
  options: { handLimit: number; recycleOrder?: readonly string[] }): PileResult & { readonly drawn: number; readonly recycled: boolean };
export declare function movePlayedCard(state: PileState, cardId: string, destination: 'draw', options: { drawIndex: number }): PileResult;
export declare function movePlayedCard(state: PileState, cardId: string, destination: Exclude<PlayedDestination, 'draw'>, options?: Readonly<Record<string, never>>): PileResult;
export declare function finishHandRound(state: PileState,
  dispositions: readonly Readonly<{ cardId: string; destination: RoundDestination }>[]): PileResult;
