import SwiftUI

enum AppTab: Hashable {
    case home
    case flights
    case deck
    case search
}

/// The app's tab bar: the same four tabs, order and icons as the React Native
/// app. The selected tab is green, the one sanctioned use of green outside live
/// data, and the bar shrinks while scrolling down.
struct RootTabView: View {
    /// Followed flights for Home, in watchlist order.
    let flights: [FlightSummary]

    @State private var selection: AppTab = .home
    @State private var query = ""

    var body: some View {
        TabView(selection: $selection) {
            Tab("Home", systemImage: "house", value: AppTab.home) {
                HomeView(flights: flights) { selection = .search }
            }

            Tab("My Flights", systemImage: "airplane", value: AppTab.flights) {
                TabPlaceholderView(title: "My Flights")
            }

            Tab("Deck", systemImage: "creditcard", value: AppTab.deck) {
                TabPlaceholderView(title: "Deck")
            }

            // The search role, with the field on the tab view itself, gives the
            // tab its own pill on iOS 26 and docks the field into the bar. The
            // field does nothing yet.
            Tab(value: AppTab.search, role: .search) {
                NavigationStack {
                    TabPlaceholderView(title: "Search")
                }
            }
        }
        .searchable(text: $query, prompt: "~/terminal:-$")
        .tint(Palette.green.color)
        .tabBarMinimizeBehavior(.onScrollDown)
    }
}

#if DEBUG
#Preview("With flights") {
    RootTabView(flights: SampleFlights.all())
}

#Preview("Empty") {
    RootTabView(flights: [])
}
#endif
