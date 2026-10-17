// Decompile every function that references a defined string exactly equal to one of the keywords.
// Usage (headless, read-only): -postScript DumpStringXrefs.java <output.txt> <keyword> [keyword...]
// @category HCZS
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class DumpStringXrefs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) throw new IllegalArgumentException("output path and keywords required");
        Set<String> keywords = new LinkedHashSet<>(Arrays.asList(args).subList(1, args.length));
        Map<Function, Set<String>> functions = new LinkedHashMap<>();
        Map<String, List<String>> sites = new LinkedHashMap<>();
        DataIterator data = currentProgram.getListing().getDefinedData(true);
        while (data.hasNext() && !monitor.isCancelled()) {
            Data item = data.next();
            Object value = item.getValue();
            if (!(value instanceof String) || !keywords.contains(value)) continue;
            for (Reference ref : getReferencesTo(item.getAddress())) {
                Address from = ref.getFromAddress();
                Function function = getFunctionContaining(from);
                sites.computeIfAbsent((String) value, k -> new ArrayList<>()).add(from + " in " + (function == null ? "?" : function.getName()));
                if (function != null) functions.computeIfAbsent(function, k -> new TreeSet<>()).add((String) value);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(args[0], StandardCharsets.UTF_8)) {
            for (String keyword : keywords)
                out.println("# " + keyword + ": " + sites.getOrDefault(keyword, List.of()));
            for (Map.Entry<Function, Set<String>> entry : functions.entrySet()) {
                Function function = entry.getKey();
                out.println("\n==== " + function.getName() + " @ " + function.getEntryPoint() + " uses " + entry.getValue());
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                out.println(result.decompileCompleted() ? result.getDecompiledFunction().getC() : "<decompile failed: " + result.getErrorMessage() + ">");
            }
        }
        decompiler.dispose();
    }
}
