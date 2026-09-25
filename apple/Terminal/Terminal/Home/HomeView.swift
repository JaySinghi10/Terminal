import SwiftUI

/// The Home tab: the ">_" mark, then the flights the person follows, or the
/// empty state when there are none.
struct HomeView: View {
    /// Followed flights, in the order the watchlist shows them.
    let flights: [FlightSummary]
    /// Called by "Add a flight" in the empty state.
    let onAddFlight: () -> Void

    /// Starts collapsed, as the React Native app did, and remembers the choice.
    @AppStorage("watchlistCollapsed") private var collapsed = true

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text(">_")
                        .textStyle(.mark)
                        .foregroundStyle(Palette.green.color)
                        .padding(.bottom, Spacing.header)
                        .accessibilityHidden(true)

                    if flights.isEmpty {
                        Spacer(minLength: Spacing.section)
                        EmptyWatchlistView(onAddFlight: onAddFlight)
                            .frame(maxWidth: .infinity)
                        Spacer(minLength: Spacing.section)
                    } else {
                        WatchlistSection(flights: flights, collapsed: $collapsed)
                    }
                }
                .padding(.horizontal, Spacing.pageMargin)
                .padding(.top, Spacing.pageTop)
                .padding(.bottom, Spacing.section)
                // Fills the screen, so the empty state can sit in the middle of
                // it; a longer list simply grows past this and scrolls.
                .frame(minHeight: proxy.size.height, alignment: .top)
            }
            .scrollIndicators(.hidden)
        }
        .background(Palette.page.color.ignoresSafeArea())
    }
}

/// What Home says when nothing is followed yet, with a way to the Search tab,
/// where a flight to follow is found.
struct EmptyWatchlistView: View {
    let onAddFlight: () -> Void

    var body: some View {
        VStack(spacing: 32) {
            Text("Flights you're following will show up here")
                .textStyle(.emptyTitle)
                .foregroundStyle(Ink.tertiary.color)
                .multilineTextAlignment(.center)

            Button(action: onAddFlight) {
                HStack(spacing: 10) {
                    Image(systemName: "plus")
                        .font(.system(size: 20, weight: .light))
                        .foregroundStyle(Palette.green.color)
                    Text("Add a flight")
                        .textStyle(.body)
                        .foregroundStyle(Ink.primary.color)
                }
                .cardSurface(horizontal: 20, vertical: Spacing.cardPadding)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 24)
    }
}

#if DEBUG
#Preview("With flights") {
    HomeView(flights: SampleFlights.all(), onAddFlight: {})
}

#Preview("Empty") {
    HomeView(flights: [], onAddFlight: {})
}
#endif
