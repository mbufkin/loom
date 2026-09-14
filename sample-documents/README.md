# Sample documents for trying Loom out

These are **inputs**, not a curriculum folder. They live outside `projects/` on
purpose: the point is to upload them yourself through the app, so the create
and add-documents steps get exercised rather than skipped.

## welding-technology-2026/

A fictional two-unit CTE course, *Introduction to Welding Technology*, invented
for testing. No real district, teacher or student appears in it.

Eleven documents, about 7,000 words, in six formats — Markdown, HTML, plain
text, RTF, PDF and Excel — so the different extraction paths all get used
rather than only the easy ones.

The text formats are checked in as they are. The PDF, the spreadsheet and the
JPEG are also checked in, so the folder works straight from a clone, but they
are generated rather than hand-made — `make_sample_binaries.py` holds their
content as reviewable code, which a binary blob in a diff would not be. Rebuild
them from the repository root with:

    python sample-documents/make_sample_binaries.py

### It is incomplete on purpose

A corpus where everything is present proves only that the audit can say "fine".
The gaps below are deliberate, so the report has something real to tell you.
Unit 1 is close to complete; Unit 2 is visibly thinner:

| | Unit 1 (SMAW) | Unit 2 (Oxy-fuel) |
|---|---|---|
| Lesson plan | yes | yes |
| Student content | yes | no |
| Assessment | yes | yes |
| Answer key | yes | **missing** |
| Vocabulary | yes | **missing** |
| Exit ticket | **missing** | **missing** |

Expect the audit to report Unit 2 as materially less complete than Unit 1, and
to flag missing exit tickets across both.

### not-supported/

One JPEG, kept out of the main folder so it is opt-in. Add it deliberately if
you want to see the refusal path: the app should answer "Loom cannot read .jpg.
Supported: doc, docx, html, md, odt, pdf, pptx, rtf, txt, xlsx" rather than
accepting it and finding it empty later.

A phone photograph of a paper handout is the unsupported file teachers actually
send, which is why it is a JPEG and not something exotic. It carries real
instructional content and no text layer at all, so it is exactly the case that
has to be caught at upload.

## How to use it

1. Open Loom, choose **Add a curriculum**, and name it (for example
   `welding-test`).
2. In **Add the documents**, use **Choose a folder** and pick
   `sample-documents/welding-technology-2026`, or drag the files onto the
   drop zone.
3. Run **Organise documents**. It should propose two units, one per unit
   prefix, and takes roughly a minute on a hosted model.
4. Check the proposed units look right, then **Start the audit**.

No school calendar is included, so pacing will be sequential rather than dated
— which is the other thing worth seeing, since it is the default anyone starts
from. `projects/_template/school-calendar.example.yaml` shows the shape if you
want to try the dated path afterwards.
