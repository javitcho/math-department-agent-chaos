from enum import Enum


class ChunkType(Enum):
    DEFINITION = "definition"
    LEMMA      = "lemma"
    THEOREM    = "theorem"
    PROOF      = "proof"
    COROLLARY  = "corollary"
    REMARK     = "remark"
    SECTION    = "section"


class ChunkStatus(Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    FLAGGED = "flagged"
    NEEDS_REWORK = "needs_rework"
    APPROVED = "approved"
    ABANDONED = "abandoned"


class SessionMode(Enum):
    SCOUT = "scout"
    DEEP = "deep"


class StoppingSignal(Enum):
    CONTINUE = "continue"
    SERENDIPITY = "serendipity"
    COUNTEREXAMPLE = "counterexample"
    CONVERGED = "converged"
    ELEGANT = "elegant"
    BUDGET = "budget"
    SCOUT_PURSUE = "scout_pursue"
    SCOUT_DROP = "scout_drop"
    SCOUT_INTERESTING = "scout_interesting"
    USER_STOP = "user_stop"
    INCUBATE = "incubate"
