// Find data words pointing at a function (vtable slots) and decompile the surrounding slots.
// Usage: -postScript DumpVtableAround.java <output.txt> <functionAddressHex> <slotsBefore> <slotsAfter>
// @category HCZS
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class DumpVtableAround extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        Address target = toAddr(Long.parseLong(args[1], 16));
        int before = Integer.parseInt(args[2]), after = Integer.parseInt(args[3]);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        Set<Address> done = new HashSet<>();
        try (PrintWriter out = new PrintWriter(args[0], StandardCharsets.UTF_8)) {
            // Thumb functions are stored with the low bit set.
            for (Address candidate : List.of(target, target.add(1))) {
                List<Address> slots = new ArrayList<>();
                for (Reference ref : getReferencesTo(candidate)) slots.add(ref.getFromAddress());
                long value = candidate.getOffset();
                String pattern = String.format("\\x%02x\\x%02x\\x%02x\\x%02x", value & 0xff, (value >> 8) & 0xff, (value >> 16) & 0xff, (value >> 24) & 0xff);
                for (Address hit : findBytes(currentProgram.getMinAddress(), pattern, 64, 4)) slots.add(hit);
                for (Address slot : new LinkedHashSet<>(slots)) {
                    if (getFunctionContaining(slot) != null) continue;
                    out.println("## slot " + slot + " -> " + candidate);
                    for (int i = -before; i <= after; i++) {
                        Address at = slot.add(4L * i);
                        long word = getInt(at) & 0xffffffffL;
                        Function function = getFunctionAt(toAddr(word & ~1L));
                        out.println("  [" + i + "] " + at + " = " + Long.toHexString(word) + " " + (function == null ? "" : function.getName()));
                        if (function == null || !done.add(function.getEntryPoint())) continue;
                        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                        out.println("==== slot " + i + " " + function.getName());
                        out.println(result.decompileCompleted() ? result.getDecompiledFunction().getC() : "<failed>");
                    }
                }
            }
        }
        decompiler.dispose();
    }
}
