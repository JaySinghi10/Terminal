// WHERE A SHEET CAN REST, IN POINTS FROM THE SCREEN'S BOTTOM EDGE.
//
// LIFTED OUT OF lib/routeResults.tsx, where the arithmetic was written for the
// route results. What moved is only the part no sheet owns: the window's top
// gap and the two ratios. The SMALL height is the one thing that differs per
// sheet, because it is cut from a head only that sheet knows -- the results
// sheet's is a grabber, a green pill and the air under it -- so it stays with
// the sheet and is passed in.
//
// THE MIDDLE AND THE LARGE are half and nine tenths of the window less 28.
// That 28 was UIKit's, measured when the results sheet was UIKit's: on an 874
// point window its middle detent settled at 423, so its maximum was 846. The
// custom sheet keeps the same two numbers so the two are the same heights on
// the same device -- 423 and 761 here.
//
// THE SHELL THAT SPRINGS BETWEEN THESE is components/DetentSheet.tsx. It takes
// any ascending list of heights; three is what both sheets in this app use.
export const SHEET_TOP_GAP = 28;
export const SHEET_MIDDLE = 0.5;
export const SHEET_LARGE = 0.9;

// Three heights, smallest first: what the shell springs between and what
// anything drawn above the sheet has to clear. barInset is what the window
// keeps at the bottom -- the tab bar and the home indicator under it, or the
// indicator alone inside a modal -- and the small height sits on top of it.
export function sheetDetents(winHeight: number, barInset: number, smallHeight: number): number[] {
  const max = Math.max(1, winHeight - SHEET_TOP_GAP);
  return [barInset + smallHeight, SHEET_MIDDLE * max, SHEET_LARGE * max];
}
