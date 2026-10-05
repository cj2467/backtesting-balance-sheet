import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workspace = "/Users/cjwork/holodeck-archive";
const inputPath = path.join(workspace, "balance-rate-nii-cof.xlsx");
const outputDir = path.join(workspace, "outputs", "01a0a8d5-e41c-7cd1-8fca-c36962c30d1e");
const outputPath = path.join(outputDir, "balance-rate-nii-cof-monthly-controlled.xlsx");
const previewDir = path.join(workspace, ".codex-tmp", "quarterly-nii", "previews-controlled");

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
const infoFill = "#E2F0D9";
const fontName = "Arial";

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows.filter((r) => r.some((v) => v !== ""));
}

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

function isoDate(date) {
  return date.toISOString().slice(0, 10);
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

const quarterDates = sourceBalance.getRange("B4:O4").values[0].map(parseQuarterHeader);
const monthDates = buildMonthDates(quarterDates);
const openingDate = monthEnd(2022, 12);
const anchorDates = [openingDate, ...quarterDates];

const anchorsText = await fs.readFile(path.join(workspace, "anchors.csv"), "utf8");
const anchorRows = parseCsv(anchorsText);
const anchorHeader = anchorRows[0];
const idxDate = anchorHeader.indexOf("period_end");
const idxConcept = anchorHeader.indexOf("concept");
const idxValue = anchorHeader.indexOf("value_usd");
const anchorMap = new Map();
for (const row of anchorRows.slice(1)) {
  const key = `${row[idxDate]}|${row[idxConcept]}`;
  const value = Number(row[idxValue]);
  if (Number.isFinite(value)) anchorMap.set(key, value / 1_000_000);
}
const anchorValue = (date, concept) => anchorMap.get(`${isoDate(date)}|${concept}`) ?? null;

const detailRows = [6, 7, 8, 10, 11, 15, 16, 17, 18];
const balanceRows = [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19];
const niiSourceRows = [6, 7, 8, 9, 10, 11, 15, 16, 17, 18];
const niiCheckRows = [...balanceRows, 21];

// Quarter-End Anchors
const anchors = workbook.worksheets.add("Quarter-End Anchors");
const anchorLastCol = "P";
setCommonSheetStyle(anchors, anchorLastCol, 31);
anchors.getRange("A1").values = [["Quarter-End Balance Anchors ($mm)"]];
anchors.getRange("A2").values = [["Reported balance-sheet controls are mapped to the average-balance categories. Loan segments and debt classes are allocated using the disclosed quarterly average mix. Blank anchors mean no comparable filing control was available."]];
anchors.getRange("A4").values = [["Line item / source control"]];
anchors.getRange("B4:P4").values = [anchorDates];
anchors.getRange("B4:P4").format.numberFormat = "mmm-yy";
anchors.getRange("A5:A21").values = sourceBalance.getRange("A5:A21").values;
anchors.getRange("A23").values = [["SOURCE CONTROLS"]];
anchors.getRange("A24:A31").values = [
  ["  Loans HFI, gross"],
  ["  Securities AFS"],
  ["  Securities HTM"],
  ["  Cash and cash equivalents"],
  ["  Interest-bearing deposits"],
  ["  Long-term debt"],
  ["  Short-term borrowings"],
  ["  Other borrowings"],
];
styleSectionRows(anchors, anchorLastCol, [5, 14, 23]);
styleTotalRows(anchors, anchorLastCol, [9, 12, 19, 21]);

const controlConcepts = [
  "loans_hfi_gross",
  "securities_afs",
  "securities_htm",
  "cash_and_equivalents",
  "deposits_interest_bearing",
  "long_term_debt",
  "short_term_borrowings",
  "other_borrowings",
];
for (let d = 0; d < anchorDates.length; d += 1) {
  const col = colLetter(d + 2);
  for (let r = 0; r < controlConcepts.length; r += 1) {
    const value = anchorValue(anchorDates[d], controlConcepts[r]);
    anchors.getRange(`${col}${24 + r}`).values = [[value]];
  }
  anchors.getRange(`${col}24:${col}31`).format.font = { name: fontName, size: 10, color: blue };
  anchors.getRange(`${col}9`).formulas = [[`=IF(ISNUMBER(${col}24),${col}24,"")`]];
  anchors.getRange(`${col}10`).formulas = [[`=IF(COUNT(${col}25:${col}26)=0,"",SUM(${col}25:${col}26))`]];
  anchors.getRange(`${col}11`).formulas = [[`=IF(ISNUMBER(${col}27),${col}27,"")`]];
  anchors.getRange(`${col}12`).formulas = [[`=IF(COUNT(${col}9:${col}11)<3,"",SUM(${col}9:${col}11))`]];
  anchors.getRange(`${col}15`).formulas = [[`=IF(ISNUMBER(${col}28),${col}28,"")`]];
  anchors.getRange(`${col}18`).formulas = [[`=IF(COUNT(${col}30:${col}31)<2,"",SUM(${col}30:${col}31))`]];
  anchors.getRange(`${col}19`).formulas = [[`=IF(COUNT(${col}15:${col}18)<4,"",SUM(${col}15:${col}18))`]];
  anchors.getRange(`${col}21`).formulas = [[`=IF(COUNT(${col}12,${col}19)<2,"",${col}12-${col}19)`]];
  if (d > 0) {
    const qCol = colLetter(d + 1);
    for (const row of [6, 7, 8]) {
      anchors.getRange(`${col}${row}`).formulas = [[`=IF(ISNUMBER(${col}9),${col}9*Balance!${qCol}${row}/Balance!${qCol}9,"")`]];
    }
    anchors.getRange(`${col}16`).formulas = [[`=IF(ISNUMBER(${col}29),${col}29*Balance!${qCol}16/SUM(Balance!${qCol}16:Balance!${qCol}17),"")`]];
    anchors.getRange(`${col}17`).formulas = [[`=IF(ISNUMBER(${col}29),${col}29*Balance!${qCol}17/SUM(Balance!${qCol}16:Balance!${qCol}17),"")`]];
  }
}
anchors.getRange("B6:P21").format.numberFormat = "$#,##0;($#,##0);-";
anchors.getRange("B24:P31").format.numberFormat = "$#,##0;($#,##0);-";
anchors.getRange("B6:P21").format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21]) anchors.getRange(`B${row}:P${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };

// Monthly EOP Balance
const monthlyEop = workbook.worksheets.add("Monthly EOP Balance");
const eopLastCol = colLetter(44);
setCommonSheetStyle(monthlyEop, eopLastCol, 21);
monthlyEop.getRange("A1").values = [["Capital One - Imputed Monthly End-of-Period Balance by line item ($mm)"]];
monthlyEop.getRange("A2").values = [["Reported quarter-end anchors are fixed where available. Month 1 and month 2 are adjusted around a straight-line path so the prior quarter-end plus all three month-ends averages to the disclosed quarterly average balance."]];
monthlyEop.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyEop.getRange(`B4:${eopLastCol}4`).values = [[openingDate, ...monthDates]];
monthlyEop.getRange(`B4:${eopLastCol}4`).format.numberFormat = "mmm-yy";
monthlyEop.getRange("A5:A21").values = sourceBalance.getRange("A5:A21").values;

for (const row of detailRows) {
  monthlyEop.getRange(`B${row}`).formulas = [[`=IF(ISNUMBER('Quarter-End Anchors'!B${row}),'Quarter-End Anchors'!B${row},Balance!B${row})`]];
  for (let q = 0; q < 14; q += 1) {
    const sourceCol = colLetter(q + 2);
    const anchorCol = colLetter(q + 3);
    const prevCol = colLetter(2 + q * 3);
    const month1Col = colLetter(3 + q * 3);
    const month2Col = colLetter(4 + q * 3);
    const month3Col = colLetter(5 + q * 3);
    monthlyEop.getRange(`${month3Col}${row}`).formulas = [[`=IF(ISNUMBER('Quarter-End Anchors'!${anchorCol}${row}),'Quarter-End Anchors'!${anchorCol}${row},2*Balance!${sourceCol}${row}-${prevCol}${row})`]];
    monthlyEop.getRange(`${month1Col}${row}`).formulas = [[`=${prevCol}${row}+(${month3Col}${row}-${prevCol}${row})/3+(2*Balance!${sourceCol}${row}-${prevCol}${row}-${month3Col}${row})`]];
    monthlyEop.getRange(`${month2Col}${row}`).formulas = [[`=${prevCol}${row}+2*(${month3Col}${row}-${prevCol}${row})/3+(2*Balance!${sourceCol}${row}-${prevCol}${row}-${month3Col}${row})`]];
  }
}
for (let c = 2; c <= 44; c += 1) {
  const col = colLetter(c);
  monthlyEop.getRange(`${col}9`).formulas = [[`=SUM(${col}6:${col}8)`]];
  monthlyEop.getRange(`${col}12`).formulas = [[`=SUM(${col}9:${col}11)`]];
  monthlyEop.getRange(`${col}19`).formulas = [[`=SUM(${col}15:${col}18)`]];
  monthlyEop.getRange(`${col}21`).formulas = [[`=${col}12-${col}19`]];
}
monthlyEop.getRange(`B6:${eopLastCol}21`).format.numberFormat = "$#,##0;($#,##0);-";
monthlyEop.getRange(`B6:${eopLastCol}19`).format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21]) monthlyEop.getRange(`B${row}:${eopLastCol}${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };
styleSectionRows(monthlyEop, eopLastCol, [5, 14]);
styleTotalRows(monthlyEop, eopLastCol, [9, 12, 19, 21]);

// Monthly Average Balance
const monthlyAvg = workbook.worksheets.add("Monthly Avg Balance");
const monthlyLastCol = colLetter(43);
setCommonSheetStyle(monthlyAvg, monthlyLastCol, 21);
monthlyAvg.getRange("A1").values = [["Capital One - Imputed Monthly Average Balance by line item ($mm)"]];
monthlyAvg.getRange("A2").values = [["Monthly average balance is the average of the prior month-end and current month-end. These balances drive monthly income allocation and monthly yields."]];
monthlyAvg.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyAvg.getRange(`B4:${monthlyLastCol}4`).values = [monthDates];
monthlyAvg.getRange(`B4:${monthlyLastCol}4`).format.numberFormat = "mmm-yy";
monthlyAvg.getRange("A5:A21").values = sourceBalance.getRange("A5:A21").values;
for (const row of balanceRows) {
  for (let m = 0; m < 42; m += 1) {
    const outCol = colLetter(m + 2);
    const prevCol = colLetter(m + 2);
    const currCol = colLetter(m + 3);
    monthlyAvg.getRange(`${outCol}${row}`).formulas = [[`=AVERAGE('Monthly EOP Balance'!${prevCol}${row},'Monthly EOP Balance'!${currCol}${row})`]];
  }
}
for (let m = 0; m < 42; m += 1) {
  const col = colLetter(m + 2);
  monthlyAvg.getRange(`${col}21`).formulas = [[`=${col}12-${col}19`]];
}
monthlyAvg.getRange(`B6:${monthlyLastCol}21`).format.numberFormat = "$#,##0;($#,##0);-";
monthlyAvg.getRange(`B6:${monthlyLastCol}21`).format.font = { name: fontName, size: 10, color: green };
for (const row of [9, 12, 19, 21]) monthlyAvg.getRange(`B${row}:${monthlyLastCol}${row}`).format.font = { name: fontName, size: 10, color: black, bold: true };
styleSectionRows(monthlyAvg, monthlyLastCol, [5, 14]);
styleTotalRows(monthlyAvg, monthlyLastCol, [9, 12, 19, 21]);

// Monthly NII
const monthlyNii = workbook.worksheets.add("Monthly NII");
setCommonSheetStyle(monthlyNii, monthlyLastCol, 21);
monthlyNii.getRange("A1").values = [["Capital One - Imputed Monthly Interest Income / Expense by line item ($mm)"]];
monthlyNii.getRange("A2").values = [["Monthly income starts from the disclosed quarterly rate on each monthly average balance. Any residual needed to match reported quarterly income is allocated in proportion to monthly average balance."]];
monthlyNii.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyNii.getRange(`B4:${monthlyLastCol}4`).values = [monthDates];
monthlyNii.getRange(`B4:${monthlyLastCol}4`).format.numberFormat = "mmm-yy";
monthlyNii.getRange("A5:A21").values = sourceNii.getRange("A5:A21").values;
for (const row of niiSourceRows) {
  for (let q = 0; q < 14; q += 1) {
    const sourceCol = colLetter(q + 2);
    const firstMonth = colLetter(2 + q * 3);
    const lastMonth = colLetter(4 + q * 3);
    const sumAvg = `SUM('Monthly Avg Balance'!${firstMonth}${row}:'Monthly Avg Balance'!${lastMonth}${row})`;
    const residual = `('Net Interest Income'!${sourceCol}${row}-${sumAvg}*Rate!${sourceCol}${row}/12)`;
    for (let j = 0; j < 3; j += 1) {
      const outCol = colLetter(2 + q * 3 + j);
      const avgCell = `'Monthly Avg Balance'!${outCol}${row}`;
      monthlyNii.getRange(`${outCol}${row}`).formulas = [[`=IF(${sumAvg}=0,"",${avgCell}*Rate!${sourceCol}${row}/12+${residual}*${avgCell}/${sumAvg})`]];
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
monthlyRate.getRange("A2").values = [["Monthly annualized rate equals monthly income or expense times 12 divided by monthly average balance. The rate reflects the disclosed quarterly rate plus the residual adjustment required to match reported quarterly income."]];
monthlyRate.getRange("A4").values = [["Line item (as disclosed)"]];
monthlyRate.getRange(`B4:${monthlyLastCol}4`).values = [monthDates];
monthlyRate.getRange(`B4:${monthlyLastCol}4`).format.numberFormat = "mmm-yy";
monthlyRate.getRange("A5:A22").values = sourceRate.getRange("A5:A22").values;
for (const row of balanceRows) {
  for (let m = 0; m < 42; m += 1) {
    const col = colLetter(m + 2);
    monthlyRate.getRange(`${col}${row}`).formulas = [[`=IF('Monthly Avg Balance'!${col}${row}=0,"",'Monthly NII'!${col}${row}*12/'Monthly Avg Balance'!${col}${row})`]];
  }
}
for (let m = 0; m < 42; m += 1) {
  const col = colLetter(m + 2);
  monthlyRate.getRange(`${col}21`).formulas = [[`=${col}12-${col}19`]];
  monthlyRate.getRange(`${col}22`).formulas = [[`=IF('Monthly Avg Balance'!${col}12=0,"",'Monthly NII'!${col}21*12/'Monthly Avg Balance'!${col}12)`]];
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
checks.getRange("A1:O65").format.font = { name: fontName, size: 10, color: black };
checks.getRange("A:A").format.columnWidth = 43;
checks.getRange("B:O").format.columnWidth = 13;
checks.getRange("A1").values = [["Controlled Monthly Imputation Checks"]];
checks.getRange("A1").format.font = { name: fontName, size: 14, bold: true, color: black };
checks.getRange("A2").values = [["Control differences should equal 0.00. Rate differences are informational because disclosed rates are rounded."]];
checks.getRange("A2").format.font = { name: fontName, size: 9, italic: true, color: gray };
const quarterLabels = quarterDates.map((d) => `Q${Math.floor(d.getUTCMonth() / 3) + 1}:${String(d.getUTCFullYear()).slice(-2)}`);
checks.getRange("A4:O4").values = [["Line item", ...quarterLabels]];
checks.getRange("A4:O4").format = { fill: headerFill, font: { name: fontName, size: 10, bold: true, color: black }, horizontalAlignment: "center" };

let checkRow = 5;
checks.getRange(`A${checkRow}:O${checkRow}`).values = [["QUARTER-END ANCHOR DIFFERENCE", ...Array(14).fill(null)]];
checks.getRange(`A${checkRow}:O${checkRow}`).format.font = { name: fontName, size: 10, bold: true, color: black };
checkRow += 1;
for (const sourceRow of balanceRows) {
  checks.getRange(`A${checkRow}`).values = [[sourceBalance.getRange(`A${sourceRow}`).values[0][0]]];
  for (let q = 0; q < 14; q += 1) {
    const outCol = colLetter(q + 2);
    const anchorCol = colLetter(q + 3);
    const eopCol = colLetter(5 + q * 3);
    checks.getRange(`${outCol}${checkRow}`).formulas = [[`=IF(ISNUMBER('Quarter-End Anchors'!${anchorCol}${sourceRow}),ROUND('Monthly EOP Balance'!${eopCol}${sourceRow}-'Quarter-End Anchors'!${anchorCol}${sourceRow},2),"")`]];
  }
  checkRow += 1;
}

checkRow += 1;
checks.getRange(`A${checkRow}:O${checkRow}`).values = [["FOUR-POINT AVERAGE BALANCE DIFFERENCE", ...Array(14).fill(null)]];
checks.getRange(`A${checkRow}:O${checkRow}`).format.font = { name: fontName, size: 10, bold: true, color: black };
checkRow += 1;
for (const sourceRow of balanceRows) {
  checks.getRange(`A${checkRow}`).values = [[sourceBalance.getRange(`A${sourceRow}`).values[0][0]]];
  for (let q = 0; q < 14; q += 1) {
    const outCol = colLetter(q + 2);
    const sourceCol = colLetter(q + 2);
    const start = colLetter(2 + q * 3);
    const finish = colLetter(5 + q * 3);
    checks.getRange(`${outCol}${checkRow}`).formulas = [[`=ROUND(SUM('Monthly EOP Balance'!${start}${sourceRow}:'Monthly EOP Balance'!${finish}${sourceRow})/4-Balance!${sourceCol}${sourceRow},2)`]];
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

checkRow += 1;
checks.getRange(`A${checkRow}:O${checkRow}`).values = [["EFFECTIVE RATE LESS DISCLOSED RATE (BPS, INFORMATIONAL)", ...Array(14).fill(null)]];
checks.getRange(`A${checkRow}:O${checkRow}`).format.font = { name: fontName, size: 10, bold: true, color: black };
const rateHeaderRow = checkRow;
checkRow += 1;
for (const sourceRow of balanceRows) {
  checks.getRange(`A${checkRow}`).values = [[sourceRate.getRange(`A${sourceRow}`).values[0][0]]];
  for (let q = 0; q < 14; q += 1) {
    const outCol = colLetter(q + 2);
    const sourceCol = colLetter(q + 2);
    checks.getRange(`${outCol}${checkRow}`).formulas = [[`=ROUND((('Net Interest Income'!${sourceCol}${sourceRow}*4/Balance!${sourceCol}${sourceRow})-Rate!${sourceCol}${sourceRow})*10000,2)`]];
  }
  checkRow += 1;
}
checks.getRange(`B6:O${rateHeaderRow - 1}`).format.numberFormat = "0.00;[Red](0.00);0.00";
checks.getRange(`B6:O${rateHeaderRow - 1}`).format.fill = checkFill;
checks.getRange(`B${rateHeaderRow + 1}:O${checkRow - 1}`).format.numberFormat = "0.00;[Red](0.00);0.00";
checks.getRange(`B${rateHeaderRow + 1}:O${checkRow - 1}`).format.fill = infoFill;
checks.freezePanes.freezeRows(4);
checks.freezePanes.freezeColumns(1);

// Notes & Sources additions
notes.getRange("A25").values = [["CONTROLLED MONTHLY IMPUTATION"]];
notes.getRange("A25").format.font = { name: fontName, size: 10, bold: true, color: black };
notes.getRange("A26:A34").values = [
  ["Quarter-End Anchors contains reported filing controls from anchors.csv. Blank anchors mean no comparable control was available."],
  ["Total loans incl. HFS uses gross HFI loans as the closest balance-sheet control. Credit card, consumer banking, and commercial banking are allocated using their quarterly average-balance mix."],
  ["Investment securities uses AFS plus HTM securities. Cash equivalents and other uses reported cash and cash equivalents as the closest control."],
  ["Securitized debt and senior/subordinated notes divide reported long-term debt using their quarterly average-balance mix. Other borrowings uses short-term plus other borrowings."],
  ["Reported quarter-end controls are fixed. Month 1 and month 2 are adjusted around a straight-line path so the four-point quarterly average equals the disclosed quarterly average balance."],
  ["Monthly Avg Balance is the two-point average of prior and current month-end balances."],
  ["Monthly NII begins with disclosed quarterly rates and allocates any residual needed to match reported quarterly income in proportion to monthly average balance."],
  ["Monthly Rate is recalculated from monthly NII and monthly average balance. Disclosed-rate differences are shown in basis points on Monthly Checks."],
  ["Monthly Checks verifies quarter-end anchors, four-point averages, and quarterly NII totals."],
];
notes.getRange("A26:A34").format.wrapText = true;

workbook.recalculate();

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const anchorInspect = await workbook.inspect({
  kind: "table",
  range: "Quarter-End Anchors!A1:P31",
  include: "values,formulas",
  tableMaxRows: 35,
  tableMaxCols: 18,
  maxChars: 16000,
});
console.log("ANCHORS");
console.log(anchorInspect.ndjson);

const checkInspect = await workbook.inspect({
  kind: "table",
  range: `Monthly Checks!A1:O${checkRow - 1}`,
  include: "values,formulas",
  tableMaxRows: 70,
  tableMaxCols: 16,
  maxChars: 22000,
});
console.log("CHECKS");
console.log(checkInspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERROR_SCAN");
console.log(errors.ndjson);

for (const sheetName of ["Quarter-End Anchors", "Monthly EOP Balance", "Monthly Avg Balance", "Monthly NII", "Monthly Rate", "Monthly Checks", "Notes & Sources"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.05, format: "png" });
  const safe = sheetName.toLowerCase().replaceAll(" ", "-").replaceAll("&", "and");
  await fs.writeFile(path.join(previewDir, `${safe}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT_PATH=${outputPath}`);
