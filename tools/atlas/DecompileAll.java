// Bulk-decompile every function of the current program into a private, greppable corpus.
//
//   args: <outdir> [threads=4] [timeout_s=30] [bucket_hex=0x40000] [limit=0]
//
// Writes (all under <outdir>, which must be a PRIVATE directory: decompiler output is a derivative of
// the vendor firmware and is never published, see docs/RE_PRIVATE.md):
//   c/<range_start>.c   functions whose entry falls in [range_start, range_start+bucket), in address order,
//                       each headed by "// ==== FUNC <addr> <name> size=<n> callers=<n> callees=<n>"
//   index.tsv           addr, size, name, ncallers, ncallees, callers, callees, strings (one row per function)
//   strings.tsv         func_addr, str_addr, string (one row per referenced string, escaped)
//   failures.tsv        addr, name, reason, seconds
//   run.log             progress and totals
//
// Open the project read-only (-readOnly) or on a copy. Nothing in the program is modified.
// Run with -noanalysis. Our own script (Caduceus repo, tools/atlas/); contains no firmware code.
// @category Caduceus
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import ghidra.util.task.TaskMonitor;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class DecompileAll extends GhidraScript {
    private final Map<Long, String> strCache = new HashMap<>();
    private Memory mem;
    private AddressSpace space;

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        File out = new File(a[0]);
        int threads = a.length > 1 ? Integer.parseInt(a[1]) : 4;
        int timeout = a.length > 2 ? Integer.parseInt(a[2]) : 30;
        long bucket = a.length > 3 ? Long.decode(a[3]) : 0x40000L;
        int limit = a.length > 4 ? Integer.parseInt(a[4]) : 0;
        new File(out, "c").mkdirs();
        mem = currentProgram.getMemory();
        space = currentProgram.getAddressFactory().getDefaultAddressSpace();
        long t0 = System.currentTimeMillis();
        PrintWriter log = new PrintWriter(new OutputStreamWriter(new FileOutputStream(new File(out, "run.log")), StandardCharsets.UTF_8), true);

        List<Function> funcs = new ArrayList<>();
        for (Function f : currentProgram.getListing().getFunctions(true)) {
            if (f.isExternal() || f.isThunk() && f.getBody().getNumAddresses() == 0) continue;
            funcs.add(f);
            if (limit > 0 && funcs.size() >= limit) break;
        }
        log.println("functions: " + funcs.size() + " threads=" + threads + " timeout=" + timeout + "s bucket=0x" + Long.toHexString(bucket));

        // ---- index pass (single thread)
        Map<Function, String> header = new HashMap<>();
        try (PrintWriter idx = utf8(new File(out, "index.tsv")); PrintWriter st = utf8(new File(out, "strings.tsv"))) {
            idx.println("addr\tsize\tname\tncallers\tncallees\tcallers\tcallees\tstrings");
            st.println("func\tstr_addr\tstring");
            int n = 0;
            for (Function f : funcs) {
                Set<Function> callers = f.getCallingFunctions(TaskMonitor.DUMMY);
                Set<Function> callees = f.getCalledFunctions(TaskMonitor.DUMMY);
                LinkedHashMap<Long, String> strs = referencedStrings(f);
                String ea = hex(f.getEntryPoint());
                long size = f.getBody().getNumAddresses();
                StringBuilder sb = new StringBuilder();
                for (Map.Entry<Long, String> e : strs.entrySet()) {
                    if (sb.length() > 0) sb.append(" \u00a6 ");
                    sb.append(esc(e.getValue()));
                    st.println(ea + "\t0x" + Long.toHexString(e.getKey()) + "\t" + esc(e.getValue()));
                }
                idx.println(ea + "\t" + size + "\t" + f.getName(true) + "\t" + callers.size() + "\t" + callees.size()
                            + "\t" + addrList(callers) + "\t" + addrList(callees) + "\t" + sb);
                header.put(f, "// ==== FUNC " + ea + " " + f.getName(true) + " size=" + size + " callers=" + callers.size()
                              + " callees=" + callees.size());
                if (++n % 10000 == 0) log.println("index " + n + " " + secs(t0) + "s");
            }
        }
        log.println("index done " + secs(t0) + "s");

        // ---- decompile pass (thread pool, one DecompInterface per worker, recycled every 4000 functions)
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        final ThreadLocal<DecompInterface[]> tl = ThreadLocal.withInitial(() -> new DecompInterface[1]);
        final ThreadLocal<int[]> uses = ThreadLocal.withInitial(() -> new int[1]);
        final List<DecompInterface> all = Collections.synchronizedList(new ArrayList<>());
        int ok = 0, fail = 0, done = 0;
        try (PrintWriter fl = utf8(new File(out, "failures.tsv"))) {
            fl.println("addr\tname\treason\tseconds");
            int i = 0;
            while (i < funcs.size()) {
                if (monitor.isCancelled()) break;
                long b0 = funcs.get(i).getEntryPoint().getOffset() / bucket * bucket;
                List<Function> chunk = new ArrayList<>();
                while (i < funcs.size() && funcs.get(i).getEntryPoint().getOffset() / bucket * bucket == b0) chunk.add(funcs.get(i++));
                List<Future<String[]>> fut = new ArrayList<>();
                for (Function f : chunk) {
                    fut.add(pool.submit(() -> {
                        DecompInterface[] h = tl.get();
                        if (h[0] == null || uses.get()[0] >= 4000) {
                            if (h[0] != null) { all.remove(h[0]); h[0].dispose(); }
                            h[0] = newDecomp(); all.add(h[0]); uses.get()[0] = 0;
                        }
                        uses.get()[0]++;
                        long s = System.currentTimeMillis();
                        try {
                            DecompileResults r = h[0].decompileFunction(f, timeout, TaskMonitor.DUMMY);
                            double el = (System.currentTimeMillis() - s) / 1000.0;
                            if (r != null && r.decompileCompleted() && r.getDecompiledFunction() != null)
                                return new String[] {r.getDecompiledFunction().getC(), null, String.valueOf(el)};
                            String why = r == null ? "null result" : (r.isTimedOut() ? "timeout" : String.valueOf(r.getErrorMessage()));
                            if (r != null && (r.isTimedOut() || r.failedToStart())) { all.remove(h[0]); h[0].dispose(); h[0] = null; }
                            return new String[] {null, why, String.valueOf(el)};
                        } catch (Exception e) {
                            all.remove(h[0]); try { h[0].dispose(); } catch (Exception ignore) {} h[0] = null;
                            return new String[] {null, "exception " + e, String.valueOf((System.currentTimeMillis() - s) / 1000.0)};
                        }
                    }));
                }
                File cf = new File(out, "c/" + String.format("%08x", b0) + ".c");
                try (PrintWriter w = utf8(cf)) {
                    w.println("// PRIVATE: Ghidra decompiler output of vendor firmware. Never publish (docs/RE_PRIVATE.md).");
                    w.println("// range 0x" + Long.toHexString(b0) + "-0x" + Long.toHexString(b0 + bucket));
                    for (int k = 0; k < chunk.size(); k++) {
                        Function f = chunk.get(k);
                        String[] r = fut.get(k).get();
                        w.println();
                        w.println(header.get(f));
                        if (r[0] != null) { w.print(r[0]); ok++; }
                        else {
                            w.println("// DECOMPILE FAILED: " + r[1].replace('\n', ' '));
                            fl.println(hex(f.getEntryPoint()) + "\t" + f.getName(true) + "\t" + r[1].replace('\n', ' ').replace('\t', ' ') + "\t" + r[2]);
                            fl.flush();
                            fail++;
                        }
                        done++;
                    }
                }
                log.println("bucket " + String.format("%08x", b0) + " n=" + chunk.size() + " done=" + done + "/" + funcs.size()
                            + " ok=" + ok + " fail=" + fail + " " + secs(t0) + "s");
            }
        } finally {
            pool.shutdownNow();
            synchronized (all) { for (DecompInterface d : all) try { d.dispose(); } catch (Exception ignore) {} }
        }
        log.println("TOTAL functions=" + funcs.size() + " ok=" + ok + " fail=" + fail + " seconds=" + secs(t0));
        log.close();
        println("DecompileAll: ok=" + ok + " fail=" + fail + " in " + secs(t0) + " s -> " + out);
    }

    private DecompInterface newDecomp() {
        DecompInterface d = new DecompInterface();
        DecompileOptions o = new DecompileOptions();
        o.grabFromProgram(currentProgram);
        d.setOptions(o);
        d.toggleCCode(true);
        d.toggleSyntaxTree(false);
        d.setSimplificationStyle("decompile");
        if (!d.openProgram(currentProgram)) throw new RuntimeException("decompiler open failed: " + d.getLastMessage());
        return d;
    }

    /** Strings a function points at: explicit references plus 32-bit scalar operands that land on a C string. */
    private LinkedHashMap<Long, String> referencedStrings(Function f) {
        LinkedHashMap<Long, String> res = new LinkedHashMap<>();
        Listing L = currentProgram.getListing();
        for (Instruction ins : L.getInstructions(f.getBody(), true)) {
            for (Reference r : ins.getReferencesFrom()) {
                Address t = r.getToAddress();
                if (t.isMemoryAddress()) addStr(res, t.getOffset());
            }
            for (int op = 0; op < ins.getNumOperands(); op++)
                for (Object o : ins.getOpObjects(op))
                    if (o instanceof Scalar) {
                        long v = ((Scalar) o).getUnsignedValue();
                        if (v >= 0x1000) addStr(res, v);
                    }
        }
        return res;
    }

    private void addStr(Map<Long, String> res, long off) {
        if (res.containsKey(off)) return;
        String s = cstr(off);
        if (s != null) res.put(off, s);
    }

    private String cstr(long off) {
        if (strCache.containsKey(off)) return strCache.get(off);
        String s = null;
        try {
            Address ad = space.getAddress(off);
            if (mem.contains(ad) && mem.getBlock(ad).isInitialized()) {
                byte[] b = new byte[256];
                int n = mem.getBytes(ad, b, 0, b.length);
                int len = 0, printable = 0, alpha = 0;
                while (len < n && b[len] != 0) {
                    int c = b[len] & 0xff;
                    if (c >= 0x20 && c < 0x7f) { printable++; if (Character.isLetter(c)) alpha++; }
                    else if (c != '\n' && c != '\r' && c != '\t') { printable = -1; break; }
                    len++;
                }
                if (printable >= 4 && len < n && alpha >= 2) s = new String(b, 0, len, StandardCharsets.US_ASCII);
            }
        } catch (Exception e) { s = null; }
        strCache.put(off, s);
        return s;
    }

    private static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r");
    }
    private static String hex(Address a) { return "0x" + a.toString(); }
    private static String addrList(Set<Function> s) {
        List<String> l = new ArrayList<>();
        for (Function f : s) l.add("0x" + f.getEntryPoint());
        Collections.sort(l);
        return String.join(",", l);
    }
    private static long secs(long t0) { return (System.currentTimeMillis() - t0) / 1000; }
    private static PrintWriter utf8(File f) throws IOException {
        return new PrintWriter(new BufferedWriter(new OutputStreamWriter(new FileOutputStream(f), StandardCharsets.UTF_8)));
    }
}
