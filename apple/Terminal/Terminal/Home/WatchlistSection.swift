import SwiftUI

/// The flights a person follows, on Home. Collapsed, it is one line naming the
/// first flight and how many more there are; expanded, a "watchlist" heading
/// over one row per flight. Tapping the line or the heading switches between
/// the two.
struct WatchlistSection: View {
    /// In the order the list shows them.
    let flights: [FlightSummary]
    @Binding var collapsed: Bool

    /// The ▸ and ▾ glyphs are a tap target rather than text, so they sit
    /// outside the type scale, at the size the React Native app drew them.
    private static let chevronFont = Font.custom(FontName.monoRegular, size: 24, relativeTo: .title)
    /// Space the collapsed line and the heading keep around themselves.
    private static let headingGap: CGFloat = 10

    var body: some View {
        if collapsed, let first = flights.first {
            Button {
                collapsed = false
            } label: {
                // The count sits outside the truncating text, so a long status
                // line is what gets cut, never "+3 more".
                HStack(alignment: .lastTextBaseline, spacing: 0) {
                    Text(collapsedLine(first: first))
                        .lineLimit(1)
                    if flights.count > 1 {
                        Text(" · +\(flights.count - 1) more")
                            .foregroundStyle(Ink.quaternary.color)
                            .fixedSize()
                    }
                }
                .textStyle(.meta)
                .padding(.vertical, Self.headingGap)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint("Shows every flight you follow")
        } else {
            VStack(alignment: .leading, spacing: 0) {
                Button {
                    collapsed = true
                } label: {
                    HStack(spacing: 8) {
                        Text("▾")
                            .font(Self.chevronFont)
                            .foregroundStyle(Ink.secondary.color)
                            .accessibilityHidden(true)
                        Text("watchlist")
                            .textStyle(.label)
                            .foregroundStyle(Ink.quaternary.color)
                    }
                    .padding(.bottom, Self.headingGap)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint("Folds the list into one line")

                VStack(spacing: Spacing.cardGap) {
                    ForEach(flights) { flight in
                        WatchlistRow(flight: flight)
                    }
                }
            }
        }
    }

    /// "▸ UA901 updated 6m ago · dep 17:25 PDT": the first flight without its
    /// status word. The count of the rest follows it separately.
    private func collapsedLine(first: FlightSummary) -> AttributedString {
        var chevron = AttributedString("▸ ")
        chevron.font = Self.chevronFont
        chevron.foregroundColor = Ink.secondary.color

        var number = AttributedString(first.flightNumber + " ")
        number.foregroundColor = Ink.primary.color

        return chevron + number + AttributedString(segments: first.statusLineWithoutHead)
    }
}

#if DEBUG
#Preview("Collapsed") {
    WatchlistSection(flights: SampleFlights.all(), collapsed: .constant(true))
        .padding(Spacing.pageMargin)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Palette.page.color)
}

#Preview("Expanded") {
    WatchlistSection(flights: SampleFlights.all(), collapsed: .constant(false))
        .padding(Spacing.pageMargin)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Palette.page.color)
}
#endif
