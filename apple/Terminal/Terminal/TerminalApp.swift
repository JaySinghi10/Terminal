//
//  TerminalApp.swift
//  Terminal
//
//  Created by Jay Singhi on 25/09/26.
//

import SwiftUI

@main
struct TerminalApp: App {
    @State private var flights = TerminalApp.startingFlights()

    var body: some Scene {
        WindowGroup {
            RootTabView(flights: flights)
        }
    }

    /// Until saved flights exist, a Debug build shows the sample flights and a
    /// Release build shows the empty Home. The samples are compiled into Debug
    /// builds only.
    private static func startingFlights() -> [FlightSummary] {
        #if DEBUG
        SampleFlights.all()
        #else
        []
        #endif
    }
}
