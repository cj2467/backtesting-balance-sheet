import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/cjwork/holodeck-archive/balance-rate-nii-cof.xlsx";
const outputDir = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e";
const outputPath = path.join(outputDir, "balance-rate-nii-cof-monthly-imputed.xlsx");
const previewDir = "/Users/cjwork/holodeck-archive/.codex-tmp/quarterly-nii/previews-monthly";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sourceBalance = workbook.worksheets.getItem("Balance");
const sourceRate = workbook.worksheets.getItem("Rate");
const sourceNii = workbook.worksheets.getItem("Net Interest Income");
const notes = workbook.worksheets.getItem("Notes & Sources");

const blue = "#0000FF";
const green = "#008000";
const black = "#000000";
const gray = "#666666";
const headerFill = "#D9E2F3";
const checkFill = "#FFF2CC";
const fontName = "Arial";

function colLetter(n) {
  let x = n;
  let out = "";
  while (x > 0) {
    const rem = (x - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    x = Math.floor((x - 1) / 26);
  }
  return out;
}

function parseQuarterHeader(value) {
  const iso = String(value).slice(0, 10);
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function monthEnd(year, monthOneBased) {
  return new Date(Date.UTC(year, monthOneBased, 0));
}

function buildMonthDates(quarterDates) {
  const months = [];
  for (const q of quarterDates) {
    const year = q.getUTCFullYear();
    const qMonth = q.getUTCMonth() + 1;
    months.push(monthEnd(year, qMonth - 2));
    months.push(monthEnd(year, qMonth - 1));
    months.push(monthEnd(year, qMonth));
  }
  return months;
}

function setCommonSheetStyle(sheet, lastCol, lastRow) {
  sheet.showGridLines = true;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font = { name: fontName, size: 10, color: black };
  sheet.getRange("A:A").format.columnWidth = 43;
  sheet.getRange(`B:${lastCol}`).format.columnWidth = 12;
  sheet.getRange(`B4:${lastCol}4`).format = {
    fill: headerFill,
    font: { name: fontName, size: 10, bold: true, color: black },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  sheet.getRange("A4").format.font = { name: fontName, size: 10, bold: true, color: black };
  sheet.getRange(`A4:${lastCol}4`).format.borders = { bottom: { style: "thin", color: "#A6A6A6" } };
  sheet.getRange("A1").format.font = { name: fontName, size: 14, bold: true, color: black };
  sheet.getRange(`A2:${lastCol}2`).format.font = { name: fontName, size: 9, italic: true, color: gray };
  sheet.getRange(`A2:${lastCol}2`).format.wrapText = true;
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 31;
  sheet.getRange(`B4:${lastCol}4`).format.numberFormat = "mmm-yy";
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(1);
}

function styleSectionRows(sheet, lastCol, rows) {
  for (const row of rows) {
    sheet.getRange(`A${row}:${lastCol}${row}`).format.font = { name: fontName, size: 10, bold: true, color: black };
    sheet.getRange(`A${row}:${lastCol}${row}`).format.borders = { bottom: { style: "thin", color: "#D9D9D9" } };
  }
}

function styleTotalRows(sheet, lastCol, rows) {
  for (const row of rows) {
    sheet.getRange(`A${row}:${lastCol}${row}`).format.font = { name: fontName, size: 10, bold: true, color: black };
    sheet.getRange(`A${row}:${lastCol}${row}`).format.borders = { bottom: { style: "thin", color: "#A6A6A6" } };
  }
}

const quarterHeaders = sourceBalance.getRange("B4:O4").values[0];
const quarterDates = quarterHeaders.map(parseQuarterHeader);
const monthDates = buildMonthDates(quarterDates);
const openingDate = monthEnd(2022, 12);

const detailRows = [6, 7, 8, 10, 11, 15, 16, 17, 18];
const niiDetailRows = [6, 7, 8, 9, 10, 11, 15, 16, 17, 18];
const balanceRows = [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19];
const niiCheckRows = [...balanceRows, 21];

// Monthly Balance
const monthlyBalance = workbook.worksheets.add("Monthly Balance");
const balanceLastCol = colLetter(44);
setCommonSheetStyle(monthlyBalance, balanceLastCol, 21);
monthlyBalance.getRange("A1").values = [["Capital One - Imputed Month-End Balance by line item ($mm)"]];
monthlyBalance.getRange("A2").values = [["Dec-22 ending balance is set equal to the Q1:23 reported average. Within each quarter, month-end balances follow a straight-line path so the prior quarter-end plus the three month-ends average to the disclosed quarterly average."]];
monthlyBalance.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyBalance.getRange(`B4:${balanceLastCol}4`).values = [[openingDate, ...monthDates]];
monthlyBalance.getRange("A5:A21").values = sourceBalance.getRange("A5:A21").values;

for (const row of detailRows) {
  monthlyBalance.getRange(`B${row}`).formulas = [[`=Balance!B${row}`]];
  for (let q = 0; q < 14; q += 1) {
    const sourceCol = colLetter(q + 2);
    const prevCol = colLetter(2 + q * 3);
    const month1Col = colLetter(3 + q * 3);
    const month2Col = colLetter(4 + q * 3);
    const month3Col = colLetter(5 + q * 3);
    monthlyBalance.getRange(`${month1Col}${row}`).formulas = [[`=${prevCol}${row}+(Balance!${sourceCol}${row}-${prevCol}${row})/1.5`]];
    monthlyBalance.getRange(`${month2Col}${row}`).formulas = [[`=${prevCol}${row}+2*(Balance!${sourceCol}${row}-${prevCol}${row})/1.5`]];
    monthlyBalance.getRange(`${month3Col}${row}`).formulas = [[`=2*Balance!${sourceCol}${row}-${prevCol}${row}`]];
  }
}
for (let c = 2; c <= 44; c += 1) {
  const col = colLetter(c);
  monthlyBalance.getRange(`${col}9`).formulas = [[`=SUM(${col}6:${col}8)`]];
  monthlyBalance.getRange(`${col}12`).formulas = [[`=SUM(${col}9:${col}11)`]];
  monthlyBalance.getRange(`${col}19`).formulas = [[`=SUM(${col}15:${col}18)`]];
  monthlyBalance.getRange(`${col}21`).formulas = [[`=${col}12-${col}19`]];
}
monthlyBalance.getRange(`B6:${balanceLastCol}21`).format.numberFormat = "$#,##0;($#,##0);-";
monthlyBalance.getRange(`B6:${balanceLastCol}19`).format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21]) monthlyBalance.getRange(`B${row}:${balanceLastCol}${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };
styleSectionRows(monthlyBalance, balanceLastCol, [5, 14]);
styleTotalRows(monthlyBalance, balanceLastCol, [9, 12, 19, 21]);

// Monthly NII
const monthlyNii = workbook.worksheets.add("Monthly NII");
const monthlyLastCol = colLetter(43);
setCommonSheetStyle(monthlyNii, monthlyLastCol, 21);
monthlyNii.getRange("A1").values = [["Capital One - Imputed Monthly Interest Income / Expense by line item ($mm)"]];
monthlyNii.getRange("A2").values = [["Each quarterly amount is allocated across its three months in proportion to two-point monthly average balance. Monthly amounts sum exactly to the disclosed quarterly interest income or expense."]];
monthlyNii.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyNii.getRange(`B4:${monthlyLastCol}4`).values = [monthDates];
monthlyNii.getRange("A5:A21").values = sourceNii.getRange("A5:A21").values;

for (const row of niiDetailRows) {
  for (let q = 0; q < 14; q += 1) {
    const sourceCol = colLetter(q + 2);
    const balStart = 2 + q * 3;
    const monthlyStart = 2 + q * 3;
    const avgTerms = [];
    for (let j = 0; j < 3; j += 1) {
      const prevBalCol = colLetter(balStart + j);
      const currBalCol = colLetter(balStart + j + 1);
      avgTerms.push(`(('Monthly Balance'!${prevBalCol}${row}+'Monthly Balance'!${currBalCol}${row})/2)`);
    }
    const denominator = avgTerms.join("+");
    for (let j = 0; j < 3; j += 1) {
      const outCol = colLetter(monthlyStart + j);
      monthlyNii.getRange(`${outCol}${row}`).formulas = [[`='Net Interest Income'!${sourceCol}${row}*${avgTerms[j]}/(${denominator})`]];
    }
  }
}
for (let c = 2; c <= 43; c += 1) {
  const col = colLetter(c);
  monthlyNii.getRange(`${col}12`).formulas = [[`=SUM(${col}9:${col}11)`]];
  monthlyNii.getRange(`${col}19`).formulas = [[`=SUM(${col}15:${col}18)`]];
  monthlyNii.getRange(`${col}21`).formulas = [[`=${col}12-${col}19`]];
}
monthlyNii.getRange(`B6:${monthlyLastCol}21`).format.numberFormat = "$#,##0.0;($#,##0.0);-";
monthlyNii.getRange(`B6:${monthlyLastCol}19`).format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21]) monthlyNii.getRange(`B${row}:${monthlyLastCol}${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };
styleSectionRows(monthlyNii, monthlyLastCol, [5, 14]);
styleTotalRows(monthlyNii, monthlyLastCol, [9, 12, 19, 21]);

// Monthly Rate
const monthlyRate = workbook.worksheets.add("Monthly Rate");
setCommonSheetStyle(monthlyRate, monthlyLastCol, 22);
monthlyRate.getRange("A1").values = [["Capital One - Imputed Monthly Yield / Rate by line item (annualized)"]];
monthlyRate.getRange("A2").values = [["Monthly annualized rate equals monthly income or expense times 12 divided by the two-point monthly average balance. Small differences from disclosed quarterly rates reflect the balance convention and source rounding."]];
monthlyRate.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyRate.getRange(`B4:${monthlyLastCol}4`).values = [monthDates];
monthlyRate.getRange("A5:A22").values = sourceRate.getRange("A5:A22").values;

for (const row of balanceRows) {
  for (let m = 0; m < 42; m += 1) {
    const outCol = colLetter(m + 2);
    const prevBalCol = colLetter(m + 2);
    const currBalCol = colLetter(m + 3);
    const avg = `( ('Monthly Balance'!${prevBalCol}${row}+'Monthly Balance'!${currBalCol}${row})/2 )`;
    monthlyRate.getRange(`${outCol}${row}`).formulas = [[`=IF(${avg}=0,"",'Monthly NII'!${outCol}${row}*12/${avg})`]];
  }
}
for (let m = 0; m < 42; m += 1) {
  const outCol = colLetter(m + 2);
  const prevBalCol = colLetter(m + 2);
  const currBalCol = colLetter(m + 3);
  const avgAssets = `( ('Monthly Balance'!${prevBalCol}12+'Monthly Balance'!${currBalCol}12)/2 )`;
  monthlyRate.getRange(`${outCol}21`).formulas = [[`=${outCol}12-${outCol}19`]];
  monthlyRate.getRange(`${outCol}22`).formulas = [[`=IF(${avgAssets}=0,"",'Monthly NII'!${outCol}21*12/${avgAssets})`]];
}
monthlyRate.getRange(`B6:${monthlyLastCol}22`).format.numberFormat = "0.00%";
monthlyRate.getRange(`B6:${monthlyLastCol}22`).format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21, 22]) monthlyRate.getRange(`B${row}:${monthlyLastCol}${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };
styleSectionRows(monthlyRate, monthlyLastCol, [5, 14]);
styleTotalRows(monthlyRate, monthlyLastCol, [9, 12, 19, 21, 22]);

// Monthly Checks
const checks = workbook.worksheets.add("Monthly Checks");
const checkLastCol = "O";
checks.showGridLines = true;
checks.getRange("A1:O40").format.font = { name: fontName, size: 10, color: black };
checks.getRange("A:A").format.columnWidth = 43;
checks.getRange("B:O").format.columnWidth = 13;
checks.getRange("A1").values = [["Monthly Imputation Checks"]];
checks.getRange("A1").format.font = { name: fontName, size: 14, bold: true, color: black };
checks.getRange("A2").values = [["All differences should equal 0.00. Checks are terminal and do not feed the monthly schedules."]];
checks.getRange("A2").format.font = { name: fontName, size: 9, italic: true, color: gray };
const quarterLabels = quarterDates.map((d) => `Q${Math.floor(d.getUTCMonth() / 3) + 1}:${String(d.getUTCFullYear()).slice(-2)}`);
checks.getRange("A4:O4").values = [["Line item", ...quarterLabels]];
checks.getRange("A4:O4").format = { fill: headerFill, font: { name: fontName, size: 10, bold: true, color: black }, horizontalAlignment: "center" };
checks.getRange("A5:O5").values = [["FOUR-POINT AVERAGE BALANCE DIFFERENCE", ...Array(14).fill(null)]];
checks.getRange("A5:O5").format.font = { name: fontName, size: 10, bold: true, color: black };

let checkRow = 6;
for (const sourceRow of balanceRows) {
  checks.getRange(`A${checkRow}`).values = [[sourceBalance.getRange(`A${sourceRow}`).values[0][0]]];
  for (let q = 0; q < 14; q += 1) {
    const outCol = colLetter(q + 2);
    const sourceCol = colLetter(q + 2);
    const monthlyStart = 2 + q * 3;
    const prev = colLetter(monthlyStart);
    const m1 = colLetter(monthlyStart + 1);
    const m2 = colLetter(monthlyStart + 2);
    const m3 = colLetter(monthlyStart + 3);
    checks.getRange(`${outCol}${checkRow}`).formulas = [[`=ROUND((SUM('Monthly Balance'!${prev}${sourceRow}:'Monthly Balance'!${m3}${sourceRow})/4)-Balance!${sourceCol}${sourceRow},2)`]];
  }
  checkRow += 1;
}

checkRow += 1;
checks.getRange(`A${checkRow}:O${checkRow}`).values = [["MONTHLY INCOME SUM DIFFERENCE", ...Array(14).fill(null)]];
checks.getRange(`A${checkRow}:O${checkRow}`).format.font = { name: fontName, size: 10, bold: true, color: black };
checkRow += 1;
for (const sourceRow of niiCheckRows) {
  checks.getRange(`A${checkRow}`).values = [[sourceNii.getRange(`A${sourceRow}`).values[0][0]]];
  for (let q = 0; q < 14; q += 1) {
    const outCol = colLetter(q + 2);
    const sourceCol = colLetter(q + 2);
    const firstMonth = colLetter(2 + q * 3);
    const lastMonth = colLetter(4 + q * 3);
    checks.getRange(`${outCol}${checkRow}`).formulas = [[`=ROUND(SUM('Monthly NII'!${firstMonth}${sourceRow}:'Monthly NII'!${lastMonth}${sourceRow})-'Net Interest Income'!${sourceCol}${sourceRow},2)`]];
  }
  checkRow += 1;
}
checks.getRange(`B6:O${checkRow - 1}`).format.numberFormat = "0.00;[Red](0.00);0.00";
checks.getRange(`B6:O${checkRow - 1}`).format.fill = checkFill;
checks.freezePanes.freezeRows(4);
checks.freezePanes.freezeColumns(1);

// Extend Notes & Sources with the imputation method.
notes.getRange("A25").values = [["MONTHLY IMPUTATION"]];
notes.getRange("A25").format.font = { name: fontName, size: 10, bold: true, color: black };
notes.getRange("A26:A30").values = [
  ["Monthly Balance starts with Dec-22 ending balance set equal to the Q1:23 reported average for each line item."],
  ["Within each quarter, month-end balances follow a straight-line path. The prior quarter-end plus the three month-ends averages to the disclosed quarterly average."],
  ["Monthly NII allocates each quarterly income or expense amount in proportion to two-point monthly average balance. The three monthly amounts sum to the disclosed quarter."],
  ["Monthly Rate is recalculated as monthly income or expense times 12 divided by two-point monthly average balance."],
  ["Monthly Checks verifies the four-point balance averages and the monthly income sums against the quarterly source."],
];
notes.getRange("A26:A30").format.wrapText = true;

workbook.recalculate();

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const balanceInspect = await workbook.inspect({
  kind: "table",
  range: "Monthly Balance!A1:AR21",
  include: "values,formulas",
  tableMaxRows: 22,
  tableMaxCols: 16,
  maxChars: 12000,
});
console.log("MONTHLY_BALANCE");
console.log(balanceInspect.ndjson);

const checkInspect = await workbook.inspect({
  kind: "table",
  range: `Monthly Checks!A1:O${checkRow - 1}`,
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 16,
  maxChars: 15000,
});
console.log("MONTHLY_CHECKS");
console.log(checkInspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERROR_SCAN");
console.log(errors.ndjson);

for (const sheetName of ["Monthly Balance", "Monthly NII", "Monthly Rate", "Monthly Checks", "Notes & Sources"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.1, format: "png" });
  const safe = sheetName.toLowerCase().replaceAll(" ", "-").replaceAll("&", "and");
  await fs.writeFile(path.join(previewDir, `${safe}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT_PATH=${outputPath}`);
