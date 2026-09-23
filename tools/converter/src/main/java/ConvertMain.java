import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwpxlib.writer.HWPXWriter;
import kr.dogfoot.hwp2hwpx.Hwp2Hwpx;
public class ConvertMain {
 public static void main(String[] args) throws Exception {
  if(args.length != 2) throw new IllegalArgumentException("input.hwp output.hwpx");
  HWPXWriter.toFilepath(Hwp2Hwpx.toHWPX(HWPReader.fromFile(args[0])), args[1]);
 }
}
