// THE SHELL OF EVERY SHEET THIS APP DRAWS ITSELF.
//
// LIFTED OUT OF components/ResultsSheet.tsx, where it was written for the route
// results and where everything about it was theirs: it read its flags and its
// heights off the route provider, drew the glass inside its own header,
// dismissed below its smallest detent and mounted by springing up from nothing.
// Each of those is a prop now. The results sheet is the shell's first consumer
// and moves exactly as it did; the tab drawer is the second.
//
// WHAT IS HERE IS THE MOTION AND NOTHING ELSE: the pan, the springs, the
// detents, the rubber band, the dismiss, the grabber, the dim, and the rule
// that a list inside the sheet may scroll only at the top. What is INSIDE the
// sheet -- its surface included -- is the consumer's.
//
// THE GESTURE MODEL. One Pan on the sheet, one Native gesture on every list
// inside it, run simultaneously. The pan works in DELTAS, not total
// translation, so who owns a frame can change mid-drag: a list may scroll
// only while the sheet is at its largest, and even then a downward delta with
// the list at offset zero belongs to the sheet. Everything the pan decides it
// decides on the UI thread; runOnJS is spent on two things only, reporting the
// settled detent and asking to close.
//
// THE PHYSICS. A critically damped spring, response 0.45s. A fling of
// SHEET_FLING or more goes one detent in its direction and never two; slower,
// the nearest detent. Above the largest detent the excess is rubber-banded on
// UIKit's own curve. Below the smallest there are two answers: a dismissible
// sheet has no band there, because that is its dismiss path -- it tracks the
// finger 1:1 and lets go at the threshold -- and a sheet that cannot be
// dismissed bands there exactly as it does at the top.
//
// TWO MODES FOR ONE HEIGHT. `translate` is what the results sheet has always
// done: a box of the largest height anchored to the screen's bottom edge, slid
// down by whatever it is short of that, so hit-testing above its top edge goes
// to whatever is behind it. `height` resizes the box instead, which costs a
// layout per frame and buys the one thing translate cannot: anything pinned to
// the box's BOTTOM stays on screen at every detent. UIKit pins a tab bar to
// the bottom of its own view, which is why the tab drawer takes this mode.
//
// A LIST REGISTERS ITSELF. The pan has to know whether a finger is on a scroll
// view and where that view is scrolled to, and it learns both from
// SheetScrollView, which a consumer renders in place of a ScrollView. The
// native gesture it declares runs simultaneously with the pan and writes the
// two shared values the pan reads. ONE PAIR FOR EVERY LIST, because one finger
// is on one list: a touch begins on the deepest scroll view under it, and that
// is the one whose offset decides the frame.
//
// THE FIVE RULES AT THE TOP OF components/swipe.tsx apply to the pan below: no
// .enabled(), no manager.fail() from a touch callback, no early returns in a
// worklet, primitives only into runOnJS.
import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { Pressable, StyleSheet, View, type ScrollViewProps } from 'react-native';
import { Gesture, GestureDetector, type PanGesture } from 'react-native-gesture-handler';
import Reanimated, {
  useSharedValue, useAnimatedStyle, useAnimatedProps, useAnimatedScrollHandler,
  withSpring, interpolate, Extrapolation, runOnJS, type SharedValue,
} from 'react-native-reanimated';
import { SHEET_SCRIM } from '../lib/glass';
import { GLASS_RADIUS } from '../lib/cards';

// ── THE SHEET'S MOTION ──────────────────────────────────────────────────────
//
// CRITICALLY DAMPED, RESPONSE 0.45s, which is the sheet UIKit draws: it lands
// and does not bounce. stiffness = (2 pi / 0.45)^2 = 195; damping = 2 sqrt(195)
// = 28 at mass 1. Overshoot is clamped so a hard fling cannot carry the sheet
// past the detent it was sent to. Not SWIPE_SPRING: that is a row's return at
// a ratio of 0.94, a different motion for a different thing.
const SHEET_SPRING = { mass: 1, stiffness: 195, damping: 28, overshootClamping: true };
// A FLING, in points per second. At or above this the sheet goes ONE detent in
// the fling's direction, never two, which is what UIKit's sheet does with a
// flick; under it the sheet settles at the nearest detent.
const SHEET_FLING = 400;
// WHEN A DRAG BELOW THE SMALL DETENT LETS GO. Released this far under it, or
// flung downward this fast at or under it, the sheet is dismissed; otherwise it
// springs back to the small detent.
const SHEET_DISMISS_BELOW = 40;
const SHEET_DISMISS_VEL = 500;
// HOW FAR A FINGER MUST KEEP GOING, in points, after a scrolling list reaches
// offset zero under it, before the sheet takes the drag. A scroll back to the
// top of a list overshoots the first row by a handful of points as a matter of
// course, and with the handover at zero points every such overshoot dragged
// the sheet down. Twenty-four is a little over two pan activations (UIKit's
// is ten): far enough that a scroll's overshoot never reaches it, short enough
// that a finger that means to pull the sheet down barely notices the wait.
// A DISTANCE, NOT A VELOCITY: the overshoot to guard against is FAST -- it is
// the tail of a flick -- so a velocity gate would let exactly the wrong drags
// through and hold back the slow deliberate ones. Only for a handover that
// happens mid-drag; a drag that begins with the list already at the top has
// nothing to overshoot and takes the sheet at once, as it always has.
const SHEET_HANDOVER_SLACK = 24;
// THE RUBBER BAND PAST THE END DETENTS, UIKit's own curve and constant:
// shown = (1 - 1 / (excess * c / d + 1)) * d, with d the sheet's own height.
const SHEET_BAND = 0.55;
// THE GRABBER, UIKit's own dimensions: 36 by 5, five points down. Its ink is
// the bubble's meta ink, an existing colour and nothing new.
const SHEET_GRABBER_W = 36;
const SHEET_GRABBER_H = 5;
const SHEET_GRABBER_TOP = 5;
const SHEET_GRABBER_INK = 'rgba(226,226,226,0.45)';

function rubber(excess: number, dimension: number): number {
  'worklet';
  return (1 - 1 / ((excess * SHEET_BAND) / dimension + 1)) * dimension;
}

// ── WHAT A LIST INSIDE THE SHEET CAN READ ───────────────────────────────────
//
// THE HEIGHT AND THE DETENTS, as shared values, because everything that reads
// them reads them on the UI thread: the results sheet's veil thins with the
// height, and every registered list may scroll only at the top. The two list
// facts and the pan are the shell's own and are not exported; SheetScrollView
// is the one thing that writes them.
type SheetMotion = {
  height: SharedValue<number>;
  detents: SharedValue<number[]>;
  listActive: SharedValue<boolean>;
  scrollY: SharedValue<number>;
  pan: PanGesture;
};

const SheetMotionContext = createContext<SheetMotion | null>(null);

function useMotion(): SheetMotion {
  const m = useContext(SheetMotionContext);
  if (m === null) throw new Error('SheetScrollView and useSheetMotion must be rendered inside DetentSheet');
  return m;
}

export function useSheetMotion(): { height: SharedValue<number>; detents: SharedValue<number[]> } {
  const { height, detents } = useMotion();
  return { height, detents };
}

export type DetentSheetProps = {
  // The heights the sheet rests at, in points from the screen's bottom edge,
  // smallest first. See lib/sheet.ts.
  detents: number[];
  // Which of them it is at. WRITTEN BY THE SHELL on every release, through
  // onDetentChange; a parent that changes it on its own moves the sheet there,
  // which is how a card opened below the fold gets the sheet raised over it.
  detent: number;
  onDetentChange: (index: number) => void;
  // See the note at the top. Read once, on mount.
  mode?: 'translate' | 'height';
  // Whether a drag below the smallest detent lets go, and whether a tap on
  // the dim closes. Read once, on mount.
  dismissible?: boolean;
  // THE OWNER ASKS TO CLOSE BY SETTING THIS, and the shell springs down and
  // reports through onDismissed when it has landed -- the owner unmounts it
  // then. A drag off the bottom asks the owner through onDismissRequest and
  // ends the same way. Setting it back to false WHILE MOUNTED is a
  // presentation that arrived mid-dismissal: the sheet springs back up.
  closing?: boolean;
  onDismissRequest?: () => void;
  onDismissed?: () => void;
  // Mounting is presentation: the sheet is at zero and springs to its detent.
  // Off, it mounts at its detent and stays there, which is what a sheet that
  // is always on screen wants.
  presentOnMount?: boolean;
  // The scrim under the sheet, faded in between the last two detents.
  dim?: boolean;
  grabber?: boolean;
  // Drawn first inside the clipped box, under the grabber and the children:
  // the results sheet's glass and veil, or a flat fill.
  surface?: ReactNode;
  children: ReactNode;
};

export function DetentSheet({
  detents, detent, onDetentChange,
  mode = 'translate', dismissible = true,
  closing = false, onDismissRequest, onDismissed,
  presentOnMount = true, dim = true, grabber = true,
  surface, children,
}: DetentSheetProps) {
  // THE HEIGHT IS THE ONE VALUE. It is how tall the sheet is, measured from the
  // screen's bottom edge, and everything else is read off it on the UI thread:
  // the transform or the box that places it, the dim, whether a list may
  // scroll, and whatever the consumer's surface makes of it. The detents are a
  // shared value too, so the gesture -- built once -- reads whatever this
  // device and rotation say they are.
  const height = useSharedValue(presentOnMount ? 0 : detents[detent]);
  const detentsSV = useSharedValue<number[]>(detents);
  // BY VALUE, NOT IDENTITY. The provider that computes the heights hands over a
  // fresh array every render; writing the shared value each time would be
  // harmless and pointless. This writes when a number changes.
  const detentsKey = detents.join(',');
  useEffect(() => {
    detentsSV.value = detents;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detentsKey]);
  // THE DRAG'S OWN BOOKKEEPING. rawH is where the finger has put the sheet
  // before the rubber band is applied; lastTy is the last translation seen, so
  // each frame is a delta. releaseV carries a fling's velocity from the worklet
  // that decided to dismiss to the effect that runs the dismissal.
  const rawH = useSharedValue(0);
  const lastTy = useSharedValue(0);
  const releaseV = useSharedValue(0);
  // THE HANDOVER'S TWO FACTS. slack is how many points of downward travel the
  // sheet still ignores after a list under the finger reached zero mid-drag --
  // SHEET_HANDOVER_SLACK at the start of a drag that began on a scrolled list,
  // zero otherwise -- and moved is whether any frame of this drag was the
  // sheet's own. A release from a drag that moved nothing does nothing: the
  // fling that ended a scroll must not be read as a fling of the sheet.
  const slack = useSharedValue(0);
  const moved = useSharedValue(false);
  // THE LIST'S TWO FACTS: where it is scrolled to, and whether a finger is on
  // it. Both are what decide, at the large detent, whether a frame belongs to
  // the list or to the sheet. Written by SheetScrollView.
  const scrollY = useSharedValue(0);
  const listActive = useSharedValue(false);

  // THE CALLBACKS, THROUGH REFS, because the gesture is built once and the
  // owner's functions may not be. Synced in an effect rather than in render,
  // which is the one place a ref may be written.
  const callbacks = useRef({ onDetentChange, onDismissRequest, onDismissed });
  useEffect(() => {
    callbacks.current = { onDetentChange, onDismissRequest, onDismissed };
  });
  // WHICH DETENT THE SHELL LAST REPORTED, so the effect on the prop below can
  // tell the owner echoing that report back from the owner asking for a move.
  const reported = useRef(detent);

  const reportDetent = (index: number) => {
    reported.current = index;
    callbacks.current.onDetentChange(index);
  };
  const askToDismiss = () => { callbacks.current.onDismissRequest?.(); };
  const finishDismiss = () => { callbacks.current.onDismissed?.(); };

  // ── PRESENTING, AND CLOSING ───────────────────────────────────────────────
  //
  // ONE EFFECT, ON ONE FLAG. Mounting is presentation: the sheet is at zero
  // and springs to its detent. closing going true is dismissal: it springs to
  // zero and, if that spring finishes, reports. And closing going back to
  // false WHILE MOUNTED is a presentation that arrived mid-dismissal -- the
  // route resolved again under a closing sheet -- so it springs back up, and
  // the cancelled spring's callback sees finished false and reports nothing.
  //
  // A SHEET THAT DOES NOT PRESENT ON MOUNT skips the first run: it was born at
  // its detent and has nowhere to spring from.
  const skipFirst = useRef(!presentOnMount);
  useEffect(() => {
    if (skipFirst.current) {
      skipFirst.current = false;
      return;
    }
    if (closing) {
      height.value = withSpring(0, { ...SHEET_SPRING, velocity: releaseV.value }, finished => {
        'worklet';
        if (finished) runOnJS(finishDismiss)();
      });
      releaseV.value = 0;
    } else {
      height.value = withSpring(detents[detent], SHEET_SPRING);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closing]);

  // ── THE OWNER MOVING THE SHEET ────────────────────────────────────────────
  //
  // The shell reports every release through onDetentChange and the owner
  // stores it; that write comes straight back here as the prop, and must not
  // be answered with a second spring -- one with no velocity, which would cut
  // the fling's own spring short. So a prop that equals the last report is the
  // echo and is ignored. Anything else is the owner asking, and is obeyed
  // unless the sheet is on its way down.
  //
  // THE IMMUTABILITY RULE IS OFF FOR ONE LINE. The height is a shared value
  // and this is the second effect to write it; the rule reads a second writer
  // of a value an earlier effect touched as a mutation it cannot order. A
  // shared value is built to be written from anywhere, and both writes are
  // springs to a target.
  useEffect(() => {
    if (reported.current === detent) return;
    reported.current = detent;
    if (closing) return;
    // eslint-disable-next-line react-hooks/immutability
    height.value = withSpring(detents[detent], SHEET_SPRING);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detent]);

  // ── THE PAN ───────────────────────────────────────────────────────────────
  //
  // WHO OWNS A FRAME. A list may scroll only at the largest detent. There,
  // with a finger on it, an upward delta or any delta while it is scrolled
  // past zero is the list's and the sheet holds still; a downward delta at
  // offset zero is the sheet's. Everywhere else every delta is the sheet's,
  // and SheetScrollView's scrollEnabled is what stops the list taking any.
  //
  // DELTAS, so the handover happens whenever the list REACHES zero mid-drag,
  // not only at the touch that started it. rawH accumulates the unbanded
  // position and the band is applied on the way to the height; while the list
  // owns a frame rawH is pinned to the sheet's real height so the next frame
  // the sheet owns starts from where it actually is.
  //
  // BUT NOT ON THE FIRST POINT PAST ZERO. A scroll back to the top overshoots
  // the first row, and handing that overshoot to the sheet dragged it down on
  // every such scroll. So a drag that began on a scrolled list is given
  // SHEET_HANDOVER_SLACK points of downward travel to spend at zero before
  // the sheet moves; those frames are the sheet's -- the list has stopped --
  // but they move nothing. A drag that began with the list at the top has no
  // slack and moves the sheet at once. The lower detents are untouched: the
  // slack exists only at the largest, which is the only place a list scrolls.
  //
  // ON RELEASE. Under the small detent past the threshold, or flung down at
  // it, a dismissible sheet asks its owner to close -- the effect above runs
  // that spring, with the fling's velocity carried across in releaseV.
  // Otherwise one detent in the fling's direction, or the nearest, and the
  // settled index is reported. A DRAG THAT NEVER MOVED THE SHEET RELEASES
  // WITH NO VELOCITY, so the flick that ended a scroll settles the sheet where
  // it already is rather than sending it a detent down.
  //
  // THE IMMUTABILITY RULE IS OFF FOR THE TWO GESTURES, and only for them. It
  // reads a shared value written inside useMemo as a render-time mutation of
  // something an effect depends on. These writes are worklets: they run on the
  // UI thread when a finger moves, never during render, and a shared value is
  // exactly the thing built to be written from there. The memo is only how the
  // gesture is built once -- a gesture object swapped under a finger loses the
  // touch.
  /* eslint-disable react-hooks/immutability */
  const pan = useMemo(
    () => Gesture.Pan()
      .onStart(e => {
        'worklet';
        lastTy.value = e.translationY;
        // Assigning the value is what cancels a spring still in flight.
        height.value = height.value;
        rawH.value = height.value;
        moved.value = false;
        // Slack only for a drag that begins on a list scrolled past zero: that
        // is the drag whose handover, if it comes, is an overshoot.
        slack.value = listActive.value && scrollY.value > 0 ? SHEET_HANDOVER_SLACK : 0;
      })
      .onUpdate(e => {
        'worklet';
        const dy = e.translationY - lastTy.value;
        lastTy.value = e.translationY;
        const ds = detentsSV.value;
        const small = ds[0];
        const large = ds[ds.length - 1];
        const atTop = height.value >= large - 0.5;
        const listOwns = atTop && listActive.value && (scrollY.value > 0 || dy < 0);
        // The frame is the sheet's but there is slack to spend first: the
        // list has stopped at zero under a finger still travelling down.
        const holding = !listOwns && atTop && listActive.value && slack.value > 0;
        if (listOwns) {
          rawH.value = height.value;
        } else if (holding) {
          slack.value = Math.max(0, slack.value - Math.max(0, dy));
          rawH.value = height.value;
        } else {
          moved.value = true;
          const raw = rawH.value - dy;
          rawH.value = raw;
          if (raw > large) {
            height.value = large + rubber(raw - large, large);
          } else if (dismissible) {
            height.value = Math.max(0, raw);
          } else if (raw < small) {
            height.value = small - rubber(small - raw, large);
          } else {
            height.value = raw;
          }
        }
      })
      // THE REFS RULE IS OFF FOR THIS CALLBACK. reportDetent and askToDismiss
      // read the callbacks ref, and the rule cannot tell that a function
      // handed to runOnJS runs on release rather than during the render that
      // built the gesture. It does: this is the release handler.
      // eslint-disable-next-line react-hooks/refs
      .onEnd(e => {
        'worklet';
        // Upward is positive from here on: the sheet's height grows as the
        // finger travels up the screen. Zero when the drag moved nothing, so
        // the release below can only settle the sheet where it stands.
        const v = moved.value ? -e.velocityY : 0;
        const h = height.value;
        const ds = detentsSV.value;
        const small = ds[0];
        const last = ds.length - 1;
        const dismiss = dismissible
          && (h < small - SHEET_DISMISS_BELOW || (h <= small + 1 && v < -SHEET_DISMISS_VEL));
        if (dismiss) {
          releaseV.value = v;
          runOnJS(askToDismiss)();
        } else {
          let idx = 0;
          if (v >= SHEET_FLING) {
            // One up: the lowest detent still clearly above the finger.
            idx = last;
            for (let i = 0; i <= last; i++) {
              if (h < ds[i] - 1) { idx = i; break; }
            }
          } else if (v <= -SHEET_FLING) {
            // One down: the highest detent still clearly below the finger.
            idx = 0;
            for (let i = last; i >= 0; i--) {
              if (h > ds[i] + 1) { idx = i; break; }
            }
          } else {
            // Nearest, ties to the lower.
            let best = Math.abs(h - ds[0]);
            for (let i = 1; i <= last; i++) {
              const d = Math.abs(h - ds[i]);
              if (d < best) { best = d; idx = i; }
            }
          }
          height.value = withSpring(ds[idx], { ...SHEET_SPRING, velocity: v });
          runOnJS(reportDetent)(idx);
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  /* eslint-enable react-hooks/immutability */

  // ── WHAT THE HEIGHT DRIVES ────────────────────────────────────────────────
  //
  // In translate mode the sheet is a box of the LARGE height anchored to the
  // screen's bottom, moved down by whatever it is short of that. In height
  // mode the box IS the height. The dim thickens between the last two detents,
  // clamped at both ends.
  const sheetStyle = useAnimatedStyle(() => (
    mode === 'height'
      ? { height: height.value }
      : { transform: [{ translateY: detentsSV.value[detentsSV.value.length - 1] - height.value }] }
  ));
  const dimStyle = useAnimatedStyle(() => {
    const ds = detentsSV.value;
    const from = ds.length > 1 ? ds[ds.length - 2] : ds[0];
    return {
      opacity: interpolate(height.value, [from, ds[ds.length - 1]], [0, 1], Extrapolation.CLAMP),
    };
  });
  // THE DIM TAKES A TOUCH ONLY AT THE LARGEST DETENT, once settled, and only
  // on a sheet that can be dismissed; then a tap on it closes the sheet, which
  // is what a tap on UIKit's dimming view does. Below that detent it is not
  // there to a finger at all, so whatever is behind the sheet is.
  const dimActive = dim && dismissible && detent === detents.length - 1 && !closing;

  const motion = useMemo<SheetMotion>(
    () => ({ height, detents: detentsSV, listActive, scrollY, pan }),
    [height, detentsSV, listActive, scrollY, pan],
  );

  return (
    <SheetMotionContext.Provider value={motion}>
      {/* ── THE DIM, UNDER THE SHEET ───────────────────────────────────────
          Rendered before the sheet so the sheet draws over it. */}
      {dim && (
        <Reanimated.View
          pointerEvents={dimActive ? 'auto' : 'none'}
          style={[StyleSheet.absoluteFill, sh.dim, dimStyle]}
        >
          <Pressable style={StyleSheet.absoluteFill} onPress={askToDismiss} />
        </Reanimated.View>
      )}

      {/* ── THE SHEET ──────────────────────────────────────────────────────
          Its two top corners carry the app's glass radius and it clips, which
          is what cuts the surface at those corners. The pan is on the whole
          of it: surface, grabber and children alike. */}
      <GestureDetector gesture={pan}>
        <Reanimated.View
          style={[
            sh.sheet,
            mode === 'translate' && { height: detents[detents.length - 1] },
            sheetStyle,
          ]}
        >
          {surface}
          {grabber && (
            <View style={sh.grabberRow} pointerEvents="none">
              <View style={sh.grabber} />
            </View>
          )}
          {children}
        </Reanimated.View>
      </GestureDetector>
    </SheetMotionContext.Provider>
  );
}

// ── A LIST THAT KNOWS IT IS IN A SHEET ──────────────────────────────────────
//
// A Native gesture on the scroll view, run simultaneously with the sheet's
// pan, so the pan can know a finger is on the list at all. It fills whatever
// the consumer gives it and scrolls only at the top -- scrollEnabled is
// animated off the sheet's own height, so at the other detents a drag on the
// rows moves the sheet. bounces is off so the list stops dead at zero and the
// sheet takes the next delta; see the pan.
//
// ITS OWN OFFSET AS WELL AS THE SHARED ONE. Two lists in one sheet each keep
// theirs, and copying it into the shared value when a finger lands is what
// stops the pan reading the other list's number.
export function SheetScrollView(props: ScrollViewProps & { children?: ReactNode }) {
  const { height, detents, listActive, scrollY, pan } = useMotion();
  const own = useSharedValue(0);
  /* eslint-disable react-hooks/immutability */
  const native = useMemo(
    () => Gesture.Native()
      .simultaneousWithExternalGesture(pan)
      .onBegin(() => { 'worklet'; listActive.value = true; scrollY.value = own.value; })
      .onFinalize(() => { 'worklet'; listActive.value = false; }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  // AND OFF FOR THE SCROLL HANDLER TOO: scrollY arrives from the context hook,
  // and the rule reads a write to anything a hook returned as a mutation. It
  // is a shared value written from a worklet, which is the one thing it is
  // for.
  const onScroll = useAnimatedScrollHandler({
    onScroll: e => { own.value = e.contentOffset.y; scrollY.value = e.contentOffset.y; },
  });
  /* eslint-enable react-hooks/immutability */
  const animatedProps = useAnimatedProps(() => ({
    scrollEnabled: height.value >= detents.value[detents.value.length - 1] - 0.5,
  }));
  return (
    <GestureDetector gesture={native}>
      <Reanimated.ScrollView
        {...props}
        animatedProps={animatedProps}
        onScroll={onScroll}
        scrollEventThrottle={16}
        bounces={false}
      />
    </GestureDetector>
  );
}

// ── THE SHELL'S OWN STYLES ──────────────────────────────────────────────────
//
// NO NEW COLOURS. The page's scrim and the glass radius are the app's own --
// see lib/cards and lib/glass.
const sh = StyleSheet.create({
  // THE SHEET'S BOX. Full width, on the screen's bottom edge; its height is set
  // inline to the largest detent in translate mode, and animated in height
  // mode. The two top corners are the app's glass radius and the box clips to
  // them, which is what cuts the surface at the corners.
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    borderTopLeftRadius: GLASS_RADIUS, borderTopRightRadius: GLASS_RADIUS,
    overflow: 'hidden',
  },
  // THE SHEETS' SCRIM, full screen under the sheet. Its opacity is the shell's.
  dim: { backgroundColor: SHEET_SCRIM },
  // THE GRABBER, centred in the clearance the consumer's head keeps above its
  // first row. A row rather than alignSelf on an absolute child, so the
  // centring is Yoga's ordinary kind.
  grabberRow: { position: 'absolute', top: SHEET_GRABBER_TOP, left: 0, right: 0, alignItems: 'center' },
  grabber: {
    width: SHEET_GRABBER_W, height: SHEET_GRABBER_H,
    borderRadius: SHEET_GRABBER_H / 2, backgroundColor: SHEET_GRABBER_INK,
  },
});
