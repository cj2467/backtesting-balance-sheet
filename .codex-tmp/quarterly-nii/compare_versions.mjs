import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const base = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e";
const files = {
  imputed: `${base}/balance-rate-nii-cof-monthly-imputed.xlsx`,
  controlled: `${base}/balance-rate-nii-cof-monthly-controlled.xlsx`,
};

for (const [label, file] of Object.entries(files)) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
  workbook.recalculate();
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table",
    include: "id,name,range,values,formulas",
    maxChars: 18000,
    tableMaxRows: 8,
    tableMaxCols: 8,
    tableMaxCellChars: 120,
  });
  console.log(`\n=== ${label.toUpperCase()} ===`);
  console.log(summary.ndjson);

  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    console.log(JSON.stringify({
      label,
      sheet: sheet.name,
      usedRange: used?.address ?? null,
      rows: used?.rowCount ?? null,
      cols: used?.columnCount ?? null,
    }));
  }

  const balanceSheet = label === "imputed" ? "Monthly Balance" : "Monthly EOP Balance";
  for (const [sheetName, range] of [
    [balanceSheet, "A4:E11"],
    [balanceSheet, "L4:N11"],
    ["Monthly NII", "A4:D11"],
    ["Monthly Checks", label === "imputed" ? "A1:O40" : "A1:O65"],
  ]) {
    const detail = await workbook.inspect({
      kind: "table",
      range: `${sheetName}!${range}`,
      include: "values,formulas",
      tableMaxRows: 70,
      tableMaxCols: 16,
      maxChars: 22000,
    });
    console.log(`--- ${label}: ${sheetName}!${range} ---`);
    console.log(detail.ndjson);
  }

  const formulaSheet = workbook.worksheets.getItem(balanceSheet);
  const niiSheet = workbook.worksheets.getItem("Monthly NII");
  console.log(JSON.stringify({
    label,
    cashOpeningQuarterValues: formulaSheet.getRange("B11:E11").values[0],
    cashOpeningQuarterFormulas: formulaSheet.getRange("B11:E11").formulas[0],
    cashOpeningQuarterNiiValues: niiSheet.getRange("B11:D11").values[0],
    cashOpeningQuarterNiiFormulas: niiSheet.getRange("B11:D11").formulas[0],
    q423CreditCardEop: formulaSheet.getRange("N6").values[0][0],
    q423CreditCardEopFormula: formulaSheet.getRange("N6").formulas[0][0],
  }, null, 2));

  if (label === "controlled") {
    const avg = workbook.worksheets.getItem("Monthly Avg Balance");
    console.log(JSON.stringify({
      controlledCashAvgQ123Values: avg.getRange("B11:D11").values[0],
      controlledCashAvgQ123Formulas: avg.getRange("B11:D11").formulas[0],
    }, null, 2));
  }
}
