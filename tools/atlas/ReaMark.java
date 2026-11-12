// Post-script (optional, only for REA): mark a BinaryLoader import the way REA's raw-binary lane expects (entry
// point plus the "REA raw binary prepared" program-info flag), so REA_GHIDRA_PROJECT_PATH can open the saved
// project.  args: <entry hex>
// Our own script (Caduceus repo, tools/atlas/, Apache-2.0). @category Caduceus
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import ghidra.program.model.symbol.SourceType;

public class ReaMark extends GhidraScript {
    @Override
    public void run() throws Exception {
        Address entry = toAddr(getScriptArgs()[0]);
        addEntryPoint(entry);
        if (getInstructionAt(entry) == null) disassemble(entry);
        Function f = getFunctionAt(entry);
        if (f == null) f = createFunction(entry, "entry");
        else if (f.getName().startsWith("FUN_")) f.setName("entry", SourceType.USER_DEFINED);
        currentProgram.getOptions(Program.PROGRAM_INFO).setBoolean("REA raw binary prepared", true);
        println("ReaMark: entry " + entry + " marked");
    }
}
