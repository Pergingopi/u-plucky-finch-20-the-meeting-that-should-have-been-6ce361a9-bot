#!/usr/bin/env python3
"""The Meeting That Should Have Been an Email — u-plucky-finch-20-the-meeting-that-should-have-been-6ce361a9.

Pure Python 3.13 standard library. The program writes one funny line
to /output/entry.txt. No network, no model call, fully deterministic:
the same code always writes the same bytes.

The line (84 characters, plus a trailing newline):

    The agenda had one item: 'Discuss the email.' The email had one
    line: 'See meeting.'

Why this line — candidates judged against the brief, funniness first,
then surprise, economy, freshness, clean wording:

* CHOSEN (84 chars): the meeting and the email point at each other
  in a circle, and neither one contains anything. The turn lands on
  the last word — "meeting" — and the laugh comes with a nod: every
  office worker has been bounced between a meeting and an email that
  each refer to the other. One idea, one loop, no filler, no
  complaint about duration, no "this could have been an email".
* Big reveal (75): "The meeting's big reveal was a slide with a
  single line: per my last email." The round-1 proposal. The
  "per my last email" punchline is a recognisable phrase, but the
  joke leans on the familiar complaint that the meeting could have
  been an email; the turn is a reference, not a surprise, and the
  laugh depends on knowing the phrase's passive-aggressive tone.
* Decide the meeting (75): "We held a meeting to decide whether
  the email needed a meeting. It did not." Self-referential and
  economical, but "It did not" is a flat verdict rather than a
  laugh: the punchline explains the joke instead of landing it.
* Ended early (82): "The meeting ended early — everyone had already
  read the email it was about." Relatable, but the turn is just
  "the email existed"; it states the obvious complaint (the meeting
  was unnecessary) without a fresh angle, and the em dash spends a
  character on throat-clearing.

Newline decision: the file ends with exactly one trailing newline.
The gate allows 1 to 200 characters; this file is 85 bytes total
including the newline, so it passes even if the scorer counts the
newline, and the line itself is a single line with no embedded
newline.

Structure of this file (revised from the round-2 builder version;
same line, same bytes out, only the internals changed):

* Validation is one small check per rule. ``check_line`` runs the
  checks in order and fails on the first one; each ``_reject_*``
  helper owns exactly one rule. Line breaking is a single rule now:
  ``_reject_line_breaks`` covers ``\\n``/``\\r`` together with the
  Unicode line and paragraph separators U+2028/U+2029, which are
  breaks in disguise. The old catch-all invisible check is split
  in two — ``_reject_format_chars`` for Cf (including the BOM) and
  ``_reject_surrogates`` for Cs — so a failure names the exact
  family that tripped it.
* The publish sequence is a class, ``AtomicPublisher``. ``main()``
  does not do four jobs at once (prepare the directory, write the
  tmp file, publish it, confirm the result); each step is a named
  method — ``prepare``, ``publish``, ``confirm`` — so a defect in
  one step can be fixed without touching the others.
* File verification is split the same way: ``_verify_stat`` owns
  the regular-file / size / mode 0644 checks and ``_verify_bytes``
  owns the byte-for-byte read-back; ``verify_file`` runs both. The
  tmp file is verified BEFORE ``os.replace`` and the published file
  again afterwards.
* The tmp sweep goes through ``_tmp_is_stale``, which owns the
  pid-parsing decision. Only pid-stamped tmp files whose owner pid
  is dead are swept; a live run's tmp is never touched. The pid
  liveness probe, ``_pid_is_alive``, treats an out-of-range pid
  (``OverflowError`` from ``os.kill``) as dead instead of crashing
  the sweep, and a pid stamp with more digits than any real pid
  can have is treated as stale — a tmp name carrying an absurd pid
  can never block a run.

Usage: mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import os
import re
import stat
import unicodedata

LINE = (
    "The agenda had one item: 'Discuss the email.' "
    "The email had one line: 'See meeting.'"
)

# Sealed gate: /output/entry.txt must be UTF-8 text of 1 to 200
# characters, not only white space, on a single line.
MAX_LINE_CHARS = 200

OUTPUT_FILENAME = "entry.txt"

# Tmp files are named .entry.txt.<pid>.tmp so concurrent runs never
# share one; the sweep below recognises exactly this shape.
_TMP_RE = re.compile(r"^\.entry\.txt\.(\d+)\.tmp$")


def _tmp_name(pid):
    """Tmp file name for a process; the pid stamp keeps concurrent
    runs in one output directory from sharing a tmp file."""
    return ".entry.txt.%d.tmp" % pid


def _reject_blank(line):
    """The line must contain something other than whitespace."""
    if not line.strip():
        raise ValueError("line must not be blank or only whitespace")


def _reject_edge_whitespace(line):
    """Leading/trailing whitespace only burns gate characters."""
    if line != line.strip():
        raise ValueError("line must not start or end with whitespace")


def _reject_line_breaks(line):
    """The entry is one line; breaks in any encoding are not allowed.

    Covers the ASCII breaks and the Unicode line and paragraph
    separators U+2028/U+2029, which are line breaks in disguise.
    """
    if "\n" in line or "\r" in line or "\u2028" in line or "\u2029" in line:
        raise ValueError("line must be a single line (no embedded newline)")


def _reject_controls(line):
    """Control characters are not text a scorer can read cleanly."""
    for ch in line:
        # Category Cc covers C0 controls, DEL and C1 controls.
        if unicodedata.category(ch) == "Cc":
            raise ValueError(
                "line must not contain control character U+%04X" % ord(ch)
            )


def _reject_format_chars(line):
    """Format characters (Cf), including the BOM, are not visible text.

    U+FEFF (BOM) is category Cf, so it is caught here; it is also
    named explicitly so a stray byte-order mark can never slip
    through on a future unicodedata table change.
    """
    for ch in line:
        if unicodedata.category(ch) == "Cf" or ch == "\ufeff":
            raise ValueError(
                "line must not contain format character U+%04X" % ord(ch)
            )


def _reject_surrogates(line):
    """Unpaired surrogates (Cs) can never be encoded as UTF-8."""
    for ch in line:
        if unicodedata.category(ch) == "Cs":
            raise ValueError(
                "line must not contain surrogate U+%04X" % ord(ch)
            )


def _reject_too_long(line):
    """The gate caps the line at MAX_LINE_CHARS characters."""
    if len(line) > MAX_LINE_CHARS:
        raise ValueError(
            "line is %d characters, over the %d-character gate"
            % (len(line), MAX_LINE_CHARS)
        )


def check_line(line):
    """Check the line against the gate; raise ValueError if it fails.

    The check runs before any file is written, so an invalid line
    fails loudly instead of producing an entry the scorer rejects.
    """
    if not isinstance(line, str):
        raise ValueError("line must be a string")
    for check in (
        _reject_blank,
        _reject_edge_whitespace,
        _reject_line_breaks,
        _reject_controls,
        _reject_format_chars,
        _reject_surrogates,
        _reject_too_long,
    ):
        check(line)
    return line


def resolve_output_dir():
    """Resolve MAKEFUN_OUTPUT_DIR defensively.

    An unset or blank value falls back to /output. A value that
    points at an existing non-directory (a regular file, a dangling
    symlink, a device) fails here with a clear message instead of
    surfacing later as a confusing makedirs/open error.
    """
    raw = os.environ.get("MAKEFUN_OUTPUT_DIR", "")
    out_dir = raw.strip() or "/output"
    if os.path.lexists(out_dir) and not os.path.isdir(out_dir):
        raise ValueError(
            "MAKEFUN_OUTPUT_DIR %r exists and is not a directory" % out_dir
        )
    return out_dir


def _pid_is_alive(pid):
    """True if pid names a process that is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A process exists but belongs to someone else: treat it
        # as alive so its tmp file is never swept away.
        return True
    except OverflowError:
        # A pid too large for the kernel names no process at all.
        return False
    except OSError:
        return True
    return True


def _tmp_is_stale(name):
    """True if a pid-stamped tmp name belongs to no live process.

    A name that matches the pattern but carries no live pid cannot
    belong to a running process, so it is safe to sweep. The caller's
    own pid is never stale to itself. A pid stamp with more digits
    than any real pid can have is stale by the same reasoning.
    """
    match = _TMP_RE.match(name)
    if not match:
        return False
    try:
        pid = int(match.group(1))
    except ValueError:
        # int() refuses absurdly long digit strings; no live
        # process can own a pid that large.
        return True
    return pid != os.getpid() and not _pid_is_alive(pid)


def _sweep_stale_temps(out_dir):
    """Remove tmp files left by earlier crashed runs, if any.

    Only files matching the pid-stamped tmp pattern are considered,
    and only when their owner pid is dead. A live run's tmp is never
    touched, and any failure to clean is best effort: a stale tmp
    must never block a fresh run.
    """
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for name in names:
        if not _tmp_is_stale(name):
            continue
        try:
            os.unlink(os.path.join(out_dir, name))
        except OSError:
            pass


def _write_fully(f, data):
    """Write every byte of data; a short write is a hard failure.

    A single ``file.write`` call is not guaranteed to consume the
    whole buffer, so loop until the view is empty and raise if a
    call ever writes zero bytes.
    """
    view = memoryview(data)
    while view:
        written = f.write(view)
        if written is None:
            # A raw writer in non-blocking mode; not expected for
            # a regular file, but never spin silently on it.
            raise OSError("write returned None without writing data")
        if written == 0:
            raise OSError("short write: wrote 0 of %d bytes" % len(view))
        view = view[written:]


def _fsync_dir(path):
    """Flush a directory entry to disk; best effort on filesystems
    that do not support it."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _verify_stat(path, data):
    """Check a file is a regular file of the right size and mode."""
    st = os.stat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("%s is not a regular file" % path)
    if st.st_size != len(data):
        raise ValueError(
            "%s is %d bytes, expected %d" % (path, st.st_size, len(data))
        )
    if stat.S_IMODE(st.st_mode) != 0o644:
        raise ValueError(
            "%s has mode %o, expected 0644" % (path, stat.S_IMODE(st.st_mode))
        )


def _verify_bytes(path, data):
    """Check a file holds exactly the bytes we meant to write."""
    with open(path, "rb") as f:
        written = f.read()
    if written != data:
        raise ValueError("read-back mismatch: %s is not the line" % path)


def verify_file(path, data):
    """Check a file is exactly the bytes we meant to write.

    Regular file, exact size, exact bytes, mode 0644. Used on the
    tmp file BEFORE the publish (so a bad write never becomes the
    entry) and again on the published file afterwards.
    """
    _verify_stat(path, data)
    _verify_bytes(path, data)


class AtomicPublisher:
    """Owns the tmp → verify → replace → verify publish sequence.

    One instance serves one run: it knows the output directory, the
    per-pid tmp path and the final path, and it guarantees the tmp
    file is cleaned up even when a step fails.
    """

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.tmp = os.path.join(out_dir, _tmp_name(os.getpid()))
        self.final = os.path.join(out_dir, OUTPUT_FILENAME)

    def prepare(self):
        """Create the output directory and sweep stale tmp files.

        Never delete the output directory itself: the grader mounts
        it, so only its contents are ever touched.
        """
        os.makedirs(self.out_dir, exist_ok=True)
        _sweep_stale_temps(self.out_dir)

    def publish(self, data):
        """Write data to tmp, verify it, then atomically replace."""
        try:
            with open(self.tmp, "wb") as f:
                _write_fully(f, data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(self.tmp, 0o644)
            # Verify BEFORE the publish: a bad write must never
            # reach the published path.
            verify_file(self.tmp, data)
            os.replace(self.tmp, self.final)
            os.chmod(self.final, 0o644)
            _fsync_dir(self.out_dir)
        finally:
            # Never leave our tmp behind, even on failure.
            try:
                os.unlink(self.tmp)
            except OSError:
                pass

    def confirm(self, data):
        """Post-publish check: the grader's file must be exact.

        The published file is checked again for regular-file type,
        exact size, exact bytes and mode 0644, and the run confirms
        its own tmp file is gone, so no stray tmp can be mistaken
        for output.
        """
        verify_file(self.final, data)
        if os.path.lexists(self.tmp):
            raise ValueError("tmp file %s still exists after publish" % self.tmp)


def main():
    check_line(LINE)
    data = (LINE + "\n").encode("utf-8")
    publisher = AtomicPublisher(resolve_output_dir())
    publisher.prepare()
    publisher.publish(data)
    publisher.confirm(data)


if __name__ == "__main__":
    main()
