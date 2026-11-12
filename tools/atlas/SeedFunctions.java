// Pre-script: disassemble and create functions at the addresses in a seeds TSV (address<TAB>anything; # comments).
// Make the TSV with:  tools/atlas/sigfind.py seeds MAIN --base B --out seeds.tsv [--extra names.json]
// Our own script (Caduceus repo, tools/atlas/, Apache-2.0). @category Caduceus
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import java.nio.file.*;
import java.util.*;

public class SeedFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        List<Address> seeds = new ArrayList<>();
        for (String l : Files.readAllLines(Paths.get(getScriptArgs()[0]))) {
            if (l.isBlank() || l.startsWith("#")) continue;
            Address a = toAddr(l.split("\t")[0].trim());
            if (currentProgram.getMemory().contains(a)) seeds.add(a);
        }
        Collections.sort(seeds);
        AddressSet set = new AddressSet();
        for (Address a : seeds) set.add(a);
        new DisassembleCommand(set, null, true).applyTo(currentProgram, monitor);
        int made = 0;
        // last to first, so a seed inside a not-yet-made neighbour doesn't get swallowed by it
        for (int i = seeds.size() - 1; i >= 0; i--) {
            monitor.checkCancelled();
            Address a = seeds.get(i);
            if (getFunctionAt(a) == null && getInstructionAt(a) != null && createFunction(a, null) != null) made++;
        }
        println("SeedFunctions: " + seeds.size() + " seeds, " + made + " functions created");
    }
}
