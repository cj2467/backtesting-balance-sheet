import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workspace = "/Users/cjwork/holodeck-archive";
const inputPath = path.join(workspace, "Controlled Forecast Quarterly and Monthly.xlsx");
const macroPath = path.join(workspace, "outputs", "01a0a8d5-e41c-7cd1-8fca-c36962c30d1e", "macro-forecast-12-month.xlsx");
const outputDir = path.join(workspace, "outputs", "01a0a8d5-e41c-7cd1-8fca-c36962c30d1e");
const outputPath = path.join(outputDir, "controlled-balance-sheet-macro-forecast.xlsx");
const previewDir = path.join(workspace, ".codex-tmp", "balance-forecast", "output-previews");

function colLetter(n) {
  let value = n;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const macroWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(macroPath));
macroWorkbook.recalculate();
const macroSource = macroWorkbook.worksheets.getItem("macro forecast");

const balance = workbook.worksheets.getItem("Balance");
const rate = workbook.worksheets.getItem("Rate");
const quarterlyNii = workbook.worksheets.getItem("Net Interest Income");
const notes = workbook.worksheets.getItem("Notes & Sources");
const anchors = workbook.worksheets.getItem("Quarter-End Anchors");
const monthlyEop = workbook.worksheets.getItem("Monthly EOP Balance");
const monthlyAvg = workbook.worksheets.getItem("Monthly Avg Balance");
const monthlyNii = workbook.worksheets.getItem("Monthly NII");
const monthlyRate = workbook.worksheets.getItem("Monthly Rate");
const checks = workbook.worksheets.getItem("Monthly Checks");

const macroHeaders = macroSource.getRange("AQ1:BC1").values[0];
const macroLabels = macroSource.getRange("A2:A24").values.flat().map(String);
const macroValues = macroSource.getRange("AQ2:BC24").values;
const macroMap = new Map(macroLabels.map((label, index) => [label, { row: index + 2, values: [...macroValues[index]] }]));
const ccMetric = macroMap.get("cc_rate_all_accounts");
ccMetric.values[0] = macroSource.getRange(`AP${ccMetric.row}`).values[0][0];

const drivers = workbook.worksheets.add("Forecast Drivers");
drivers.showGridLines = false;
drivers.getRange("A1").values = [["Macro-driven balance sheet forecast"]];
drivers.getRange("A2").values = [["Actuals end June 2025. The macro path covers July 2025 through June 2026 and feeds the monthly balance, yield and NII schedules."]];
drivers.getRange("A4:N4").values = [["Macro driver", ...macroHeaders]];

const driverMetrics = [
  ["fed_funds_eff", "Fed funds effective rate"],
  ["ust_5y", "5-year Treasury yield"],
  ["ust_10y", "10-year Treasury yield"],
  ["prime_rate", "Prime rate"],
  ["case_shiller_nsa_adj", "Case-Shiller index, adjusted"],
  ["mortgage_30y_fixed", "30-year mortgage rate"],
  ["unemployment_rate", "Unemployment rate"],
  ["nonfarm_payrolls_k", "Nonfarm payrolls (000s)"],
  ["bbb_corp_oas", "BBB corporate OAS"],
  ["cc_rate_all_accounts", "Credit card rate, all accounts"],
];

for (let index = 0; index < driverMetrics.length; index += 1) {
  const [metric, label] = driverMetrics[index];
  drivers.getRange(`A${5 + index}:N${5 + index}`).values = [[label, ...macroMap.get(metric).values]];
}
drivers.getRange("A15").values = [["Credit card rate used"]];
drivers.getRange("B15").formulas = [["=B14"]];
for (let col = 3; col <= 14; col += 1) {
  const letter = colLetter(col);
  const prior = colLetter(col - 1);
  drivers.getRange(`${letter}15`).formulas = [[`=IF(ISNUMBER(${letter}14),${letter}14,${prior}15)`]];
}

drivers.getRange("A17:B17").values = [["MODEL CALIBRATION", null]];
drivers.getRange("A18:A28").values = [
  ["Cash / interest-bearing deposits at Jun-25"],
  ["Securitized debt monthly runoff"],
  ["Deposit beta to Fed funds"],
  ["Credit card yield spread vs card rate"],
  ["Consumer yield spread vs mortgage rate"],
  ["Commercial yield spread vs prime rate"],
  ["Securities yield spread vs 5-year Treasury"],
  ["Cash yield spread vs Fed funds"],
  ["Securitized debt spread vs 5-year Treasury"],
  ["Senior note spread vs 5-year Treasury + BBB OAS"],
  ["Other borrowing spread vs Fed funds"],
];
drivers.getRange("B18").formulas = [["='Monthly EOP Balance'!AF11/'Monthly EOP Balance'!AF15"]];
drivers.getRange("B19").values = [[0.005]];
drivers.getRange("B20").formulas = [["='Monthly Rate'!AE15/(B5/100)"]];
drivers.getRange("B21").formulas = [["='Monthly Rate'!AE6-(B15/100)"]];
drivers.getRange("B22").formulas = [["='Monthly Rate'!AE7-(B10/100)"]];
drivers.getRange("B23").formulas = [["='Monthly Rate'!AE8-(B8/100)"]];
drivers.getRange("B24").formulas = [["='Monthly Rate'!AE10-(B6/100)"]];
drivers.getRange("B25").formulas = [["='Monthly Rate'!AE11-(B5/100)"]];
drivers.getRange("B26").formulas = [["='Monthly Rate'!AE16-(B6/100)"]];
drivers.getRange("B27").formulas = [["='Monthly Rate'!AE17-(B6/100)-(B13/100)"]];
drivers.getRange("B28").formulas = [["='Monthly Rate'!AE18-(B5/100)"]];
drivers.getRange("A30:A32").values = [
  ["Balance mapping: card, commercial and deposits follow payrolls; consumer follows Case-Shiller; investment securities, senior notes and other borrowings remain flat."],
  ["Cash preserves its June 2025 share of deposits. Securitized debt runs off at the editable monthly rate above."],
  ["Yield mapping: each forecast benchmark keeps its June 2025 product spread; deposit costs retain their June 2025 beta to Fed funds."],
];

const darkBlue = "#4472C4";
const headerFill = "#D9E2F3";
const forecastFill = "#EAF2F8";
const inputBlue = "#0000FF";
const formulaGreen = "#008000";
const black = "#000000";
const gray = "#666666";
const fontName = "Arial";

drivers.getRange("A1").format.font = { name: fontName, size: 14, bold: true, color: black };
drivers.getRange("A2:N2").format.font = { name: fontName, size: 9, italic: true, color: gray };
drivers.getRange("A2:N2").format.wrapText = true;
drivers.getRange("A2:N2").format.rowHeight = 28;
drivers.getRange("A4:N4").format = {
  fill: darkBlue,
  font: { name: fontName, size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
drivers.getRange("A5:A15").format.font = { name: fontName, size: 10, color: black };
drivers.getRange("B5:N14").format.font = { name: fontName, size: 10, color: inputBlue };
drivers.getRange("C4:N15").format.fill = forecastFill;
drivers.getRange("B15:N15").format.font = { name: fontName, size: 10, color: black };
drivers.getRange("A17:B17").format = {
  fill: headerFill,
  font: { name: fontName, size: 10, bold: true, color: black },
};
drivers.getRange("A18:A28").format.font = { name: fontName, size: 10, color: black };
drivers.getRange("B18:B18").format.font = { name: fontName, size: 10, color: formulaGreen };
drivers.getRange("B19").format.font = { name: fontName, size: 10, color: inputBlue };
drivers.getRange("B20:B28").format.font = { name: fontName, size: 10, color: formulaGreen };
drivers.getRange("A30:A32").format.font = { name: fontName, size: 9, italic: true, color: gray };
drivers.getRange("A30:A32").format.wrapText = true;
drivers.getRange("A30:A32").format.rowHeight = 36;
drivers.getRange("A:A").format.columnWidth = 48;
drivers.getRange("B:N").format.columnWidth = 12;
drivers.getRange("B5:N11").format.numberFormat = "0.00";
drivers.getRange("B12:N12").format.numberFormat = "#,##0";
drivers.getRange("B13:N15").format.numberFormat = "0.00";
drivers.getRange("B18:B28").format.numberFormat = "0.00%";
drivers.freezePanes.freezeRows(4);
drivers.freezePanes.freezeColumns(1);

const balanceRows = [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 21];
const detailAssetRows = [6, 7, 8, 10, 11];
const detailLiabilityRows = [15, 16, 17, 18];

for (let monthIndex = 0; monthIndex < 12; monthIndex += 1) {
  const eopCol = colLetter(33 + monthIndex);
  const previousEopCol = colLetter(32 + monthIndex);
  const driverCol = colLetter(3 + monthIndex);
  const previousDriverCol = colLetter(2 + monthIndex);
  const avgCol = colLetter(32 + monthIndex);

  monthlyEop.getRange(`${eopCol}6`).formulas = [[`=${previousEopCol}6*('Forecast Drivers'!${driverCol}12/'Forecast Drivers'!${previousDriverCol}12)*((1-'Forecast Drivers'!${driverCol}11/100)/(1-'Forecast Drivers'!${previousDriverCol}11/100))`]];
  monthlyEop.getRange(`${eopCol}7`).formulas = [[`=${previousEopCol}7*('Forecast Drivers'!${driverCol}9/'Forecast Drivers'!${previousDriverCol}9)`]];
  monthlyEop.getRange(`${eopCol}8`).formulas = [[`=${previousEopCol}8*('Forecast Drivers'!${driverCol}12/'Forecast Drivers'!${previousDriverCol}12)`]];
  monthlyEop.getRange(`${eopCol}9`).formulas = [[`=SUM(${eopCol}6:${eopCol}8)`]];
  monthlyEop.getRange(`${eopCol}10`).formulas = [[`=${previousEopCol}10`]];
  monthlyEop.getRange(`${eopCol}15`).formulas = [[`=${previousEopCol}15*('Forecast Drivers'!${driverCol}12/'Forecast Drivers'!${previousDriverCol}12)`]];
  monthlyEop.getRange(`${eopCol}11`).formulas = [[`=${eopCol}15*'Forecast Drivers'!$B$18`]];
  monthlyEop.getRange(`${eopCol}12`).formulas = [[`=SUM(${eopCol}9:${eopCol}11)`]];
  monthlyEop.getRange(`${eopCol}16`).formulas = [[`=${previousEopCol}16*(1-'Forecast Drivers'!$B$19)`]];
  monthlyEop.getRange(`${eopCol}17`).formulas = [[`=${previousEopCol}17`]];
  monthlyEop.getRange(`${eopCol}18`).formulas = [[`=${previousEopCol}18`]];
  monthlyEop.getRange(`${eopCol}19`).formulas = [[`=SUM(${eopCol}15:${eopCol}18)`]];
  monthlyEop.getRange(`${eopCol}21`).formulas = [[`=${eopCol}12-${eopCol}19`]];

  for (const row of [...detailAssetRows, ...detailLiabilityRows]) {
    monthlyAvg.getRange(`${avgCol}${row}`).formulas = [[`=AVERAGE('Monthly EOP Balance'!${previousEopCol}${row},'Monthly EOP Balance'!${eopCol}${row})`]];
  }
  monthlyAvg.getRange(`${avgCol}9`).formulas = [[`=SUM(${avgCol}6:${avgCol}8)`]];
  monthlyAvg.getRange(`${avgCol}12`).formulas = [[`=SUM(${avgCol}9:${avgCol}11)`]];
  monthlyAvg.getRange(`${avgCol}19`).formulas = [[`=SUM(${avgCol}15:${avgCol}18)`]];
  monthlyAvg.getRange(`${avgCol}21`).formulas = [[`=${avgCol}12-${avgCol}19`]];

  monthlyRate.getRange(`${avgCol}6`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}15/100+'Forecast Drivers'!$B$21)`]];
  monthlyRate.getRange(`${avgCol}7`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}10/100+'Forecast Drivers'!$B$22)`]];
  monthlyRate.getRange(`${avgCol}8`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}8/100+'Forecast Drivers'!$B$23)`]];
  monthlyRate.getRange(`${avgCol}9`).formulas = [[`=('Monthly Avg Balance'!${avgCol}6*${avgCol}6+'Monthly Avg Balance'!${avgCol}7*${avgCol}7+'Monthly Avg Balance'!${avgCol}8*${avgCol}8)/'Monthly Avg Balance'!${avgCol}9`]];
  monthlyRate.getRange(`${avgCol}10`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}6/100+'Forecast Drivers'!$B$24)`]];
  monthlyRate.getRange(`${avgCol}11`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}5/100+'Forecast Drivers'!$B$25)`]];
  monthlyRate.getRange(`${avgCol}12`).formulas = [[`=('Monthly Avg Balance'!${avgCol}9*${avgCol}9+'Monthly Avg Balance'!${avgCol}10*${avgCol}10+'Monthly Avg Balance'!${avgCol}11*${avgCol}11)/'Monthly Avg Balance'!${avgCol}12`]];
  monthlyRate.getRange(`${avgCol}15`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}5/100*'Forecast Drivers'!$B$20)`]];
  monthlyRate.getRange(`${avgCol}16`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}6/100+'Forecast Drivers'!$B$26)`]];
  monthlyRate.getRange(`${avgCol}17`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}6/100+'Forecast Drivers'!${driverCol}13/100+'Forecast Drivers'!$B$27)`]];
  monthlyRate.getRange(`${avgCol}18`).formulas = [[`=MAX(0,'Forecast Drivers'!${driverCol}5/100+'Forecast Drivers'!$B$28)`]];
  monthlyRate.getRange(`${avgCol}19`).formulas = [[`=('Monthly Avg Balance'!${avgCol}15*${avgCol}15+'Monthly Avg Balance'!${avgCol}16*${avgCol}16+'Monthly Avg Balance'!${avgCol}17*${avgCol}17+'Monthly Avg Balance'!${avgCol}18*${avgCol}18)/'Monthly Avg Balance'!${avgCol}19`]];
  monthlyRate.getRange(`${avgCol}21`).formulas = [[`=${avgCol}12-${avgCol}19`]];

  for (const row of [...detailAssetRows, ...detailLiabilityRows]) {
    monthlyNii.getRange(`${avgCol}${row}`).formulas = [[`='Monthly Avg Balance'!${avgCol}${row}*'Monthly Rate'!${avgCol}${row}/12`]];
  }
  monthlyNii.getRange(`${avgCol}9`).formulas = [[`=SUM(${avgCol}6:${avgCol}8)`]];
  monthlyNii.getRange(`${avgCol}12`).formulas = [[`=SUM(${avgCol}9:${avgCol}11)`]];
  monthlyNii.getRange(`${avgCol}19`).formulas = [[`=SUM(${avgCol}15:${avgCol}18)`]];
  monthlyNii.getRange(`${avgCol}21`).formulas = [[`=${avgCol}12-${avgCol}19`]];
  monthlyRate.getRange(`${avgCol}22`).formulas = [[`='Monthly NII'!${avgCol}21*12/'Monthly Avg Balance'!${avgCol}12`]];
}

const quarterConfigs = [
  { quarterCol: "L", checkCol: "L", avgStart: "AF", avgEnd: "AH", eopStart: "AF", eopEnd: "AI", anchorCol: "M", quarterEop: "AI" },
  { quarterCol: "M", checkCol: "M", avgStart: "AI", avgEnd: "AK", eopStart: "AI", eopEnd: "AL", anchorCol: "N", quarterEop: "AL" },
  { quarterCol: "N", checkCol: "N", avgStart: "AL", avgEnd: "AN", eopStart: "AL", eopEnd: "AO", anchorCol: "O", quarterEop: "AO" },
  { quarterCol: "O", checkCol: "O", avgStart: "AO", avgEnd: "AQ", eopStart: "AO", eopEnd: "AR", anchorCol: "P", quarterEop: "AR" },
];

for (const config of quarterConfigs) {
  for (const row of balanceRows) {
    balance.getRange(`${config.quarterCol}${row}`).formulas = [[`=SUM('Monthly EOP Balance'!${config.eopStart}${row}:'Monthly EOP Balance'!${config.eopEnd}${row})/4`]];
    anchors.getRange(`${config.anchorCol}${row}`).formulas = [[`='Monthly EOP Balance'!${config.quarterEop}${row}`]];
  }
  for (const row of [...detailAssetRows, 9, 12, ...detailLiabilityRows, 19, 21]) {
    quarterlyNii.getRange(`${config.quarterCol}${row}`).formulas = [[`=SUM('Monthly NII'!${config.avgStart}${row}:'Monthly NII'!${config.avgEnd}${row})`]];
  }
  for (const row of [6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19]) {
    rate.getRange(`${config.quarterCol}${row}`).formulas = [[`=IF(Balance!${config.quarterCol}${row}=0,"",'Net Interest Income'!${config.quarterCol}${row}*4/Balance!${config.quarterCol}${row})`]];
  }
  rate.getRange(`${config.quarterCol}21`).formulas = [[`=${config.quarterCol}12-${config.quarterCol}19`]];
  rate.getRange(`${config.quarterCol}22`).formulas = [[`='Net Interest Income'!${config.quarterCol}21*4/Balance!${config.quarterCol}12`]];
}

anchors.getRange("M24:P31").clear({ applyTo: "contents" });
quarterlyNii.getRange("L24:O25").clear({ applyTo: "contents" });

balance.getRange("L4:O4").values = [["2025-09-30 (F)", "2025-12-31 (F)", "2026-03-31 (F)", "2026-06-30 (F)"]];
rate.getRange("L4:O4").values = [["2025-09-30 (F)", "2025-12-31 (F)", "2026-03-31 (F)", "2026-06-30 (F)"]];
quarterlyNii.getRange("L4:O4").values = [["2025-09-30 (F)", "2025-12-31 (F)", "2026-03-31 (F)", "2026-06-30 (F)"]];

balance.getRange("A2").values = [["Average balance over the quarter. Actuals through Q2:25; Q3:25–Q2:26 forecast from the macro-driven monthly schedule."]];
rate.getRange("A2").values = [["Annualised yield on assets and cost of funds on liabilities. Actuals through Q2:25; forecast rates retain June 2025 benchmark spreads or betas."]];
quarterlyNii.getRange("A2").values = [["Interest income on assets and interest expense on liabilities. Actuals through Q2:25; forecast quarters sum the macro-driven monthly schedule."]];
anchors.getRange("A2").values = [["Reported balance-sheet controls through Jun-25. Forecast quarter ends thereafter link to the monthly balance forecast; filing source controls are intentionally blank."]];
monthlyEop.getRange("A2").values = [["Reported and controlled month ends through Jun-25. Jul-25 through Jun-26 is a macro-driven balance forecast."]];
monthlyAvg.getRange("A2").values = [["Monthly average balance is the average of prior and current month end. Forecast months begin Jul-25."]];
monthlyNii.getRange("A2").values = [["Monthly interest income or expense equals monthly average balance times annualized forecast rate divided by 12."]];
monthlyRate.getRange("A2").values = [["Actual yields through Jun-25. Forecast yields use the Macro Drivers benchmark path plus June 2025 product spreads or betas."]];
checks.getRange("A2").values = [["Actual controls run through Q2:25. Forecast columns thereafter verify quarter-end links, four-point averages and monthly NII sums."]];
checks.getRange("A48").values = [["EFFECTIVE RATE LESS QUARTERLY RATE (BPS, INFORMATIONAL)"]];

notes.getRange("A36").values = [["MACRO-DRIVEN FORECAST"]];
notes.getRange("A36").format.font = { name: fontName, size: 10, bold: true, color: black };
notes.getRange("A37:A42").values = [
  ["Actuals end June 2025. Forecast period is July 2025 through June 2026."],
  ["Credit card balances follow payroll growth adjusted for the employment-rate ratio. Consumer banking follows the adjusted Case-Shiller index. Commercial banking and interest-bearing deposits follow payroll growth."],
  ["Investment securities, senior notes and other borrowings remain flat. Cash holds its June 2025 share of deposits. Securitized debt runs off 0.5% per month; this is the only editable forecast assumption."],
  ["Forecast yields use the provided macro benchmark path plus June 2025 product spreads. Deposit cost retains the June 2025 beta to Fed funds."],
  ["Quarterly average balances use the established four-point convention. Quarterly NII sums monthly NII, and quarterly rates are recomputed from quarterly NII and average balance."],
  ["Macro inputs and calibration values are shown on Forecast Drivers."],
];
notes.getRange("A37:A42").format.wrapText = true;

function styleForecastRange(sheet, headerRange, bodyRange, formulaColor = formulaGreen) {
  sheet.getRange(headerRange).format.fill = forecastFill;
  sheet.getRange(headerRange).format.font = { name: fontName, size: 10, bold: true, color: black };
  sheet.getRange(bodyRange).format.fill = forecastFill;
  sheet.getRange(bodyRange).format.font = { name: fontName, size: 10, color: formulaColor };
}

styleForecastRange(balance, "L4:O4", "L6:O21", black);
styleForecastRange(rate, "L4:O4", "L6:O22", black);
styleForecastRange(quarterlyNii, "L4:O4", "L6:O25", black);
styleForecastRange(anchors, "M4:P4", "M6:P31", formulaGreen);
styleForecastRange(monthlyEop, "AG4:AR4", "AG6:AR21", formulaGreen);
styleForecastRange(monthlyAvg, "AF4:AQ4", "AF6:AQ21", formulaGreen);
styleForecastRange(monthlyNii, "AF4:AQ4", "AF6:AQ21", formulaGreen);
styleForecastRange(monthlyRate, "AF4:AQ4", "AF6:AQ22", formulaGreen);

for (const sheet of [balance, rate, quarterlyNii, anchors, monthlyEop, monthlyAvg, monthlyNii, monthlyRate]) {
  sheet.getRange("A2").format.font = { name: fontName, size: 9, italic: true, color: gray };
  sheet.getRange("A2").format.wrapText = true;
}

workbook.recalculate();

const forecastChecks = await workbook.inspect({
  kind: "table",
  range: "Monthly Checks!L4:O60",
  include: "values,formulas",
  tableMaxRows: 65,
  tableMaxCols: 6,
  maxChars: 18000,
});
console.log("FORECAST CHECKS");
console.log(forecastChecks.ndjson);

for (const [sheetName, rangeAddress] of [
  ["Forecast Drivers", "A1:N32"],
  ["Balance", "I1:O21"],
  ["Rate", "I1:O22"],
  ["Net Interest Income", "I1:O27"],
  ["Quarter-End Anchors", "K1:P31"],
  ["Monthly EOP Balance", "AD1:AR21"],
  ["Monthly Avg Balance", "AC1:AQ21"],
  ["Monthly NII", "AC1:AQ21"],
  ["Monthly Rate", "AC1:AQ22"],
  ["Monthly Checks", "J1:O60"],
  ["Notes & Sources", "A25:A42"],
]) {
  const inspect = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!${rangeAddress}`,
    include: "values,formulas",
    tableMaxRows: 65,
    tableMaxCols: 20,
    maxChars: 14000,
  });
  console.log(`INSPECT ${sheetName}`);
  console.log(inspect.ndjson);
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, rangeAddress] of [
  ["Forecast Drivers", "A1:N32"],
  ["Balance", "I1:O21"],
  ["Rate", "I1:O22"],
  ["Net Interest Income", "I1:O27"],
  ["Quarter-End Anchors", "K1:P31"],
  ["Monthly EOP Balance", "AD1:AR21"],
  ["Monthly Avg Balance", "AC1:AQ21"],
  ["Monthly NII", "AC1:AQ21"],
  ["Monthly Rate", "AC1:AQ22"],
  ["Monthly Checks", "J1:O60"],
  ["Notes & Sources", "A25:A42"],
]) {
  const preview = await workbook.render({ sheetName, range: rangeAddress, scale: 1.25, format: "png" });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "-").replaceAll("&", "and");
  await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
reopened.recalculate();
const reopenedDrivers = reopened.worksheets.getItem("Forecast Drivers");
const reopenedEop = reopened.worksheets.getItem("Monthly EOP Balance");
const reopenedBalance = reopened.worksheets.getItem("Balance");
const eopBefore = reopenedEop.getRange("AG6").values[0][0];
const quarterBefore = reopenedBalance.getRange("L6").values[0][0];
const payrollBefore = reopenedDrivers.getRange("C12").values[0][0];
reopenedDrivers.getRange("C12").values = [[payrollBefore + 500]];
reopened.recalculate();
const eopAfter = reopenedEop.getRange("AG6").values[0][0];
const quarterAfter = reopenedBalance.getRange("L6").values[0][0];
const reopenedErrors = await reopened.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "reopened workbook formula error scan",
});

console.log(JSON.stringify({
  outputPath,
  recalculationTest: {
    eopBefore,
    eopAfter,
    quarterBefore,
    quarterAfter,
    changed: eopBefore !== eopAfter && quarterBefore !== quarterAfter,
  },
  reopenedErrors: reopenedErrors.ndjson,
}, null, 2));
