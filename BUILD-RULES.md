# Build rules

The constraints every script in this repository follows. They are written down because
a rule that only lives in someone's head gets broken by the next build.

## The script is the source of truth

The workflow JSON is output. To change a workflow, change the script and run it again.
Hand editing the JSON works right up until the next build overwrites it.

If a workflow is ever edited inside n8n and re-exported, the script and the file have
diverged, and one of them has to win. Saying so out loud at that moment is part of the
rule.

## Built-in n8n nodes, and a Code node has to earn its place

Edit Fields, Switch, Filter, IF, the drag-in AI nodes, pinned data and a disabled node
come first. If a built-in node can do the job, it gets used even when a few lines of
JavaScript would be shorter.

The reason is maintenance rather than taste. A canvas someone else can read is a canvas
someone else can change. There are no Code nodes anywhere in this repository, and the
build scripts check for that on every run.

## Fewest nodes that still tell the story

Node names are the narration. Someone should be able to follow the canvas without
opening a single node.

## Pinned data instead of mock branches

n8n pins sample data onto a node directly, so a workflow can be opened and run without
credentials, live accounts or a parallel test path cluttering the canvas. Every workflow
here ships with its sample records pinned.

## Arithmetic before judgement

Where a decision can be made by comparing numbers, it is made by comparing numbers.
A model is asked only for the part that genuinely needs language.

## Four sticky notes at most

The notes on the canvas describe what the workflow does and name the sample record that
demonstrates each rule. Anything longer belongs in a README.
