import SwiftUI

/// Stands in for a tab that has not been built yet.
struct TabPlaceholderView: View {
    let title: String

    var body: some View {
        Text(title)
            .textStyle(.title)
            .foregroundStyle(Ink.tertiary.color)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Palette.page.color.ignoresSafeArea())
    }
}

#if DEBUG
#Preview {
    TabPlaceholderView(title: "My Flights")
}
#endif
