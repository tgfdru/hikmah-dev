// Reads the stored fields of Shamela's page index (Lucene 10.4) without the
// postings files, so only the text files (~4.8 GB of the 13 GB database) are needed.
//
//   java -cp lucene-core-10.4.0.jar:. ShamelaDump <index dir> sample
//   java -cp lucene-core-10.4.0.jar:. ShamelaDump <index dir> <book_ids.txt> > pages.jsonl
//
// Output: one JSON object per page with every stored field (strings and numbers).
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.apache.lucene.codecs.*;
import org.apache.lucene.index.*;
import org.apache.lucene.store.*;

public class ShamelaDump {
  static String esc(String s) {
    StringBuilder b = new StringBuilder(s.length() + 16);
    for (char c : s.toCharArray()) {
      switch (c) {
        case '"': b.append("\\\""); break;
        case '\\': b.append("\\\\"); break;
        case '\n': b.append("\\n"); break;
        case '\r': b.append("\\r"); break;
        case '\t': b.append("\\t"); break;
        default: if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
      }
    }
    return b.toString();
  }

  public static void main(String[] args) throws Exception {
    Path dir = Paths.get(args[0]);
    boolean sample = args[1].equals("sample");
    Set<String> books = new HashSet<>();
    if (!sample) for (String l : Files.readAllLines(Paths.get(args[1]))) if (!l.isBlank()) books.add(l.trim());
    PrintStream out = new PrintStream(new BufferedOutputStream(new FileOutputStream(FileDescriptor.out), 1 << 20), false, "UTF-8");
    try (Directory d = FSDirectory.open(dir)) {
      SegmentInfos infos = SegmentInfos.readLatestCommit(d);
      int printed = 0; long kept = 0, seen = 0;
      for (SegmentCommitInfo ci : infos) {
        SegmentInfo si = ci.info;
        Codec codec = si.getCodec();
        Directory sd = si.getUseCompoundFile() ? codec.compoundFormat().getCompoundReader(d, si) : d;
        FieldInfos fis = codec.fieldInfosFormat().read(sd, si, "", IOContext.DEFAULT);
        try (StoredFieldsReader r = codec.storedFieldsFormat().fieldsReader(sd, si, fis, IOContext.DEFAULT)) {
          for (int doc = 0; doc < si.maxDoc(); doc++) {
            seen++;
            Map<String, String> f = new LinkedHashMap<>();
            r.document(doc, new StoredFieldVisitor() {
              public Status needsField(FieldInfo fi) { return Status.YES; }
              public void stringField(FieldInfo fi, String v) { f.put(fi.name, "\"" + esc(v) + "\""); }
              public void intField(FieldInfo fi, int v) { f.put(fi.name, Integer.toString(v)); }
              public void longField(FieldInfo fi, long v) { f.put(fi.name, Long.toString(v)); }
              public void floatField(FieldInfo fi, float v) { f.put(fi.name, Float.toString(v)); }
              public void doubleField(FieldInfo fi, double v) { f.put(fi.name, Double.toString(v)); }
            });
            if (sample) {
              if (printed++ < 3) {
                for (Map.Entry<String, String> e : f.entrySet()) {
                  String v = e.getValue();
                  System.err.println(si.name + " " + e.getKey() + " = " + (v.length() > 160 ? v.substring(0, 160) + "…" : v));
                }
                System.err.println("---");
              }
              continue;
            }
            String id = f.getOrDefault("id", "\"\"").replace("\"", "");
            String book = id.contains("-") ? id.substring(0, id.indexOf('-')) : id;
            if (!books.contains(book)) continue;
            StringBuilder line = new StringBuilder("{");
            for (Map.Entry<String, String> e : f.entrySet()) {
              if (line.length() > 1) line.append(',');
              line.append('"').append(esc(e.getKey())).append("\":").append(e.getValue());
            }
            out.println(line.append('}'));
            kept++;
          }
        }
        if (sample && printed >= 3) break;
      }
      out.flush();
      System.err.println("pages seen " + seen + ", kept " + kept);
    }
  }
}
