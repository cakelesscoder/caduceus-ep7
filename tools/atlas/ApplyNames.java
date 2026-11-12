// Apply Caduceus atlas.json + autonames.json names to your own Ghidra import of an OM/Olympus main image.
// Java twin of apply_names.py, for headless runs without PyGhidra. Same rules, same arguments:
//
//   args: <atlas.json|-> [autonames.json|-] [-create] [-comments] [-force] [-min-conf low|medium|high]
//
//   atlas.json   authoritative: func symbols rename the function at addr (USER_DEFINED); table/data/struct become
//                labels. With -create, a func address that has no function becomes one when it looks like an
//                entry (task entry, call target, or not inside another function); otherwise it gets a label.
//   autonames    proposals: rename only functions that still carry a default (FUN_) or analysis name, source
//                ANALYSIS, so your own names always win. Rows below -min-conf (default low = all) are skipped.
//   -comments    put the atlas sig/notes into the plate comment (only where none exists).
//   -force       rename even user-named functions.
//   "Class::method" names go into a class namespace.
// Headless: analyzeHeadless <proj_dir> <proj> -process -noanalysis -scriptPath tools/atlas
//           -postScript ApplyNames.java docs/atlas.json docs/autonames.json -create
// Our own script (Caduceus repo, tools/atlas/). @category Caduceus
import com.google.gson.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.app.util.NamespaceUtils;
import ghidra.util.exception.DuplicateNameException;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class ApplyNames extends GhidraScript {
    private final Map<String, Integer> stat = new TreeMap<>();
    private boolean force;

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String atlas = a.length > 0 ? a[0] : "-", auto = a.length > 1 ? a[1] : "-";
        boolean create = false, comments = false;
        int minConf = 0;
        for (int i = 2; i < a.length; i++) {
            if (a[i].equals("-create")) create = true;
            else if (a[i].equals("-comments")) comments = true;
            else if (a[i].equals("-force")) force = true;
            else if (a[i].equals("-min-conf")) minConf = conf(a[++i]);
        }
        if (!atlas.equals("-")) {
            for (JsonElement e : read(atlas).getAsJsonArray("symbols")) {
                JsonObject s = e.getAsJsonObject();
                Address ad = addr(s.get("addr").getAsString());
                String name = s.get("name").getAsString(), kind = s.get("kind").getAsString();
                String sig = str(s, "sig"), notes = str(s, "notes");
                if (ad == null || !currentProgram.getMemory().contains(ad)) { bump("atlas: address not in memory"); continue; }
                if (kind.equals("func")) {
                    Function f = getFunctionAt(ad);
                    if (f == null && create && looksLikeEntry(ad, name, sig)) {
                        if (getInstructionAt(ad) == null && getInstructionContaining(ad) == null) disassemble(ad);
                        f = getInstructionAt(ad) == null ? null : createFunction(ad, null);
                        bump(f != null ? "atlas: function created" : "atlas: create failed");
                    }
                    if (f != null) rename(f, name, SourceType.USER_DEFINED, "atlas: function renamed");
                    else label(ad, name, SourceType.USER_DEFINED, "atlas: label (no function entry)");
                } else label(ad, name, SourceType.USER_DEFINED, "atlas: label " + kind);
                if (comments && (sig.length() + notes.length()) > 0 && getPlateComment(ad) == null)
                    setPlateComment(ad, "atlas: " + name + (sig.isEmpty() ? "" : "\n" + sig) + (notes.isEmpty() ? "" : "\n" + notes));
            }
        }
        if (!auto.equals("-")) {
            for (JsonElement e : read(auto).getAsJsonArray("names")) {
                JsonObject s = e.getAsJsonObject();
                if (s.get("method").getAsString().equals("atlas")) continue;   // applied above, from the source
                if (conf(s.get("confidence").getAsString()) < minConf) { bump("auto: below min-conf"); continue; }
                Address ad = addr(s.get("addr").getAsString());
                Function f = ad == null ? null : getFunctionAt(ad);
                if (f == null) { bump("auto: no function at addr"); continue; }
                SourceType src = f.getSymbol().getSource();
                if (!force && (src == SourceType.USER_DEFINED || src == SourceType.IMPORTED)) { bump("auto: kept existing name"); continue; }
                rename(f, s.get("name").getAsString(), SourceType.ANALYSIS, "auto: renamed " + s.get("method").getAsString());
            }
        }
        for (Map.Entry<String, Integer> e : stat.entrySet()) println(String.format("%6d  %s", e.getValue(), e.getKey()));
    }

    private boolean looksLikeEntry(Address ad, String name, String sig) {
        if (sig.contains("entry") || name.startsWith("task_")) return true;
        for (Reference r : getReferencesTo(ad)) if (r.getReferenceType().isCall()) return true;
        return getFunctionContaining(ad) == null;
    }

    private void rename(Function f, String full, SourceType src, String what) throws Exception {
        if (!force && src == SourceType.ANALYSIS && f.getSymbol().getSource() == SourceType.USER_DEFINED) { bump("kept user name"); return; }
        String[] p = split(full);
        Namespace ns = p[0] == null ? currentProgram.getGlobalNamespace()
            : NamespaceUtils.createNamespaceHierarchy(p[0], null, currentProgram, src);
        try { f.getSymbol().setNameAndNamespace(p[1], ns, src); }
        catch (DuplicateNameException x) { f.getSymbol().setNameAndNamespace(p[1] + "_" + f.getEntryPoint(), ns, src); }
        bump(what);
    }

    private void label(Address ad, String full, SourceType src, String what) throws Exception {
        String[] p = split(full);
        Namespace ns = p[0] == null ? currentProgram.getGlobalNamespace()
            : NamespaceUtils.createNamespaceHierarchy(p[0], null, currentProgram, src);
        Symbol s = currentProgram.getSymbolTable().createLabel(ad, p[1], ns, src);
        s.setPrimary();
        bump(what);
    }

    private static String[] split(String full) {
        int i = full.lastIndexOf("::");
        return i < 0 ? new String[] {null, full} : new String[] {full.substring(0, i), full.substring(i + 2)};
    }
    private Address addr(String s) { try { return toAddr(Long.decode(s)); } catch (Exception e) { return null; } }
    private static String str(JsonObject o, String k) { return o.has(k) && !o.get(k).isJsonNull() ? o.get(k).getAsString() : ""; }
    private static int conf(String c) { return c.equals("high") ? 2 : c.equals("medium") ? 1 : 0; }
    private void bump(String k) { stat.merge(k, 1, Integer::sum); }
    private static JsonObject read(String p) throws IOException {
        try (Reader r = new InputStreamReader(new FileInputStream(p), StandardCharsets.UTF_8)) { return JsonParser.parseReader(r).getAsJsonObject(); }
    }
}
