# Candidate Target Markets

## Selection Criteria

A suitable first customer should have:

1. A repeated visual inspection task
2. A reasonably stable camera position
3. Visible defects or assembly errors
4. Existing manual inspection
5. Financial impact from missed defects or unnecessary rejection
6. Access to normal and defective samples
7. A domain expert who can define acceptance
8. A decision that does not initially require safety certification

## Candidate 1 — Packaging and Label Inspection

Possible inspections:

- missing or incorrect labels
- damaged packaging
- incorrect printing
- missing components
- cap or seal problems
- incorrect fill presentation

Advantages:

- Images are comparatively easy to collect
- The inspection decision is easy to explain
- Product appearance is often controlled
- Errors can cause returns and wasted batches
- A demonstration can be created without expensive hardware

Risks:

- Some problems may be better solved with barcode or rule-based vision
- Reflective packaging creates lighting problems
- Product varieties may require separate configurations

## Candidate 2 — Tiles, Stone and Manufactured Surfaces

Possible inspections:

- cracks
- scratches
- stains
- discoloration
- edge damage
- abnormal surface texture

Advantages:

- Strong match with visual anomaly detection
- MVTec tile can be used during platform development
- Products can often be photographed from a fixed position
- Defects may directly affect product grading and price

Risks:

- Natural variation can generate false positives
- Surface appearance changes with lighting
- Some structural defects are not visible in ordinary photographs

## Candidate 3 — Assembly Completeness

Possible inspections:

- missing component
- incorrect orientation
- incorrect color or part
- incomplete assembly
- misplaced fastener
- packaging completeness

Advantages:

- Clear business decision
- Often easier than open-ended defect classification
- Normal reference images are valuable
- Errors can be demonstrated visually

Risks:

- Every product variation requires configuration
- Camera alignment matters
- Some tasks may be solvable with conventional computer vision

## Initial Recommendation

Begin customer discovery with packaging/label inspection and manufactured
surface inspection.

Use MVTec tile only as engineering data for developing the reusable platform.
Do not present benchmark data as customer validation.

The final first market will be selected based on customer access, data
availability, financial pain and willingness to run a pilot.