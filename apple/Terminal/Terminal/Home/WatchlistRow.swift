import SwiftUI

/// One followed flight on Home: the number, the route in cities and the date on
/// the first line, the status line under it.
///
/// At the accessibility text sizes one line cannot hold all three, so the route
/// moves to a line of its own and the status line wraps instead of cutting off
/// the countdown.
struct WatchlistRow: View {
    let flight: FlightSummary

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let stacked = typeSize.isAccessibilitySize

        VStack(alignment: .leading, spacing: Spacing.line) {
            HStack(spacing: 0) {
                Text(flight.flightNumber)
                    .textStyle(.code)
                    .foregroundStyle(Ink.primary.color)
                    .fixedSize()

                if stacked {
                    Spacer(minLength: 8)
                } else {
                    route
                        .padding(.leading, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if let date = DateLabel.route(flight.flightDate) {
                    Text(date)
                        .textStyle(.metaBold)
                        .foregroundStyle(Ink.tertiary.color)
                        .fixedSize()
                        .padding(.leading, 8)
                }
            }

            if stacked {
                route
            }

            StatusLineView(segments: flight.statusLine, lineLimit: stacked ? nil : 1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface()
        .accessibilityElement(children: .combine)
    }

    /// Cut in the middle when it is too long: losing the middle of both names is
    /// better than losing the destination.
    private var route: some View {
        Text(flight.routeText)
            .textStyle(.data)
            .foregroundStyle(Ink.tertiary.color)
            .lineLimit(1)
            .truncationMode(.middle)
    }
}

#if DEBUG
#Preview("Standard text") {
    VStack(spacing: Spacing.cardGap) {
        ForEach(SampleFlights.all()) { flight in
            WatchlistRow(flight: flight)
        }
    }
    .padding(Spacing.pageMargin)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    .background(Palette.page.color)
}

#Preview("Accessibility text") {
    ScrollView {
        VStack(spacing: Spacing.cardGap) {
            ForEach(SampleFlights.all()) { flight in
                WatchlistRow(flight: flight)
            }
        }
        .padding(Spacing.pageMargin)
    }
    .background(Palette.page.color)
    .dynamicTypeSize(.accessibility3)
}
#endif
