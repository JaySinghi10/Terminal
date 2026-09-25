import SwiftUI

extension AttributedString {
    /// Status segments as coloured runs of one string, so a status line wraps
    /// and truncates as a single line of text.
    init(segments: [StatusSegment]) {
        self.init()
        for segment in segments {
            var run = AttributedString(segment.text)
            run.foregroundColor = segment.tone.color
            append(run)
        }
    }
}

/// The second line of a watchlist row: the status word first, then what
/// follows it, each run in its own colour.
struct StatusLineView: View {
    let segments: [StatusSegment]
    /// One line in a row at standard text sizes; nil lets it wrap.
    var lineLimit: Int? = 1

    var body: some View {
        Text(AttributedString(segments: segments))
            .textStyle(.meta)
            .lineLimit(lineLimit)
    }
}

#if DEBUG
#Preview {
    VStack(alignment: .leading, spacing: 12) {
        ForEach(SampleFlights.all()) { flight in
            StatusLineView(segments: flight.statusLine)
        }
    }
    .padding(Spacing.pageMargin)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(Palette.page.color)
}
#endif
