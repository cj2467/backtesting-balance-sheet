import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = "/Users/cjwork/holodeck-archive/balance-rate-nii-cof.xlsx";
const previewDir = "/Users/cjwork/holodeck-archive/.codex-tmp/quarterly-nii/previews-existing";
await fs.mkdir(previewDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const overview = await workbook.inspect({
  kind: "workbook,sheet,table,formula",
  maxChars: 18000,
  tableMaxRows: 30,
  tableMaxCols: 20,
  options: { maxResults: 200 },
});
console.log(overview.ndjson);

for (const name of ["Balance", "Rate", "Net Interest Income", "Notes & Sources"]) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1.2, format: "png" });
  await fs.writeFile(`${previewDir}/${name.toLowerCase().replaceAll(" ", "-").replaceAll("&", "and")}.png`, new Uint8Array(await preview.arrayBuffer()));
}
