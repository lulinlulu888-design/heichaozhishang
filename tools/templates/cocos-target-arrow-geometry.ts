/** Static port of this APK's drawArrow geometry; see native-target-arrow-evidence.json.
 * Coordinates are source-style Y-up. This is not a bit-exact ARM float emulator.
 */
export type ArrowPoint = { x: number; y: number };
export type ArrowGeometry = {
    positions: number[]; uvs: number[]; indices: number[];
    endWidthAngleDegrees: number; nativeHeadRotationDegrees: number;
};
const SOURCE_PI = Math.fround(3.14);

function tangentAngle(dx: number, dy: number, fraction: number): number {
    const length = Math.hypot(dx, dy);
    const height = dx / 4;
    const slope = 4 * height / length - 8 * height * fraction / length;
    return (Math.atan2(slope, 1) + Math.atan2(dy, dx)) * 180 / SOURCE_PI;
}

function sidePoints(start: ArrowPoint, end: ArrowPoint, count: number): ArrowPoint[] | null {
    const dx = end.x - start.x, dy = end.y - start.y;
    const length = Math.hypot(dx, dy);
    if (length === 0) return null;
    const nx = -dy / length, ny = dx / length, height = dx / 4;
    const points: ArrowPoint[] = [];
    // Source starts at i=1, not 0, and includes the end point.
    for (let i = 1; i <= count; i++) {
        const t = i / count;
        const offset = height * (1 - 4 * (t - .5) ** 2);
        points.push({ x: start.x + dx * t + nx * offset, y: start.y + dy * t + ny * offset });
    }
    return points;
}

export function createTargetArrowGeometry(start: ArrowPoint, end: ArrowPoint): ArrowGeometry | null {
    if (![start.x, start.y, end.x, end.y].every(Number.isFinite)) return null;
    const dx = end.x - start.x, dy = end.y - start.y;
    // Reconstruction guard: do not render near-coincident points. The native angle helper
    // also skips L<0.1, but its caller's complete degenerate behavior is not reproduced.
    if (Math.hypot(dx, dy) < .1) return null;
    const endAngle = tangentAngle(dx, dy, 1);
    const headAngle = tangentAngle(dx, dy, 21 / 20);
    const radians = endAngle / 180 * SOURCE_PI;
    const tx = 10 * Math.sin(radians), ty = 10 * Math.cos(radians);
    const count = 60;
    const right = sidePoints({ x: start.x + 80, y: start.y }, { x: end.x + tx, y: end.y - ty }, count);
    const left = sidePoints({ x: start.x - 80, y: start.y }, { x: end.x - tx, y: end.y + ty }, count);
    if (!right || !left) return null;
    const positions: number[] = [], uvs: number[] = [], indices: number[] = [];
    for (let i = 0; i < count; i++) {
        positions.push(right[i].x, right[i].y, 0, left[i].x, left[i].y, 0);
        // Source divides pair index by total vertex count minus one.
        const v = i / (count * 2 - 1);
        uvs.push(0, v, 1, v);
    }
    // Native expands each consecutive triple. Preserve vertex order; the material must
    // use no face culling because winding alternates along this triangle strip.
    for (let i = 0; i < count * 2 - 2; i++) indices.push(i, i + 1, i + 2);
    if (!positions.every(Number.isFinite)) return null;
    return { positions, uvs, indices, endWidthAngleDegrees: endAngle, nativeHeadRotationDegrees: -headAngle };
}
