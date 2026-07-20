# Lesson-rung method bake-off

**Dataset:** `dallas-career-2026`  
**Lessons scored:** 33  
**Methods:** s1_completeness, s3_curriculum_own  
**Total model calls:** 0

Each method reduces a lesson to a 0-1 signal (presence -> coverage; band -> mean band / max). This is a comparison of METHODS, not a grade of the lessons.

## Per-lesson scores by method

| Lesson | Unit | s1_completeness | s3_curriculum_own | Divergence |
|---|---|---|---|---|
| Copy of Business Marketing Finance - Slides | business-marketing | 0.75 | 0.50 | 0.25 |
| Law and Public Service Lesson Plans | law-and-public-service | 0.62 | 0.38 | 0.25 |
| Skills for Success-Career Ready - Slides | professional-preparedness | 0.62 | 0.38 | 0.25 |
| Agriculture- Plant Science Alternate Lesson Plan Template | agriculture | 0.62 | 0.75 | 0.12 |
| Architecture Construction Lesson Plan | architecture-construction | 0.50 | 0.38 | 0.12 |
| Arts A V Tech Lesson Plan | arts-av-technology | 0.50 | 0.62 | 0.12 |
| Arts AV Technology Communication - Slides | arts-av-technology | 0.88 | 0.75 | 0.12 |
| Business Marketing Finance Lesson Plan | business-marketing | 0.12 | 0.25 | 0.12 |
| CTSO Lesson Plan | career-cluster | 0.25 | 0.38 | 0.12 |
| Career Cluster - Lesson Plan | career-cluster | 0.12 | 0.25 | 0.12 |
| Week One Lesson Plan | career-cluster | 0.50 | 0.38 | 0.12 |
| Career Exploration Slides | career-exploration | 0.62 | 0.75 | 0.12 |
| Dallas ISD High School Options - Lesson Plan | dallas-isd | 0.25 | 0.38 | 0.12 |
| Dallas ISD High School Options - Slides | dallas-isd | 0.62 | 0.75 | 0.12 |
| Engineering Lesson | engineering | 0.62 | 0.50 | 0.12 |
| Engineering Lesson Plan | engineering | 0.25 | 0.12 | 0.12 |
| Family and Community Wellness-Human Services - Lesson Plan | family-community | 0.25 | 0.38 | 0.12 |
| Family and Community Wellness-Human Services - Slides | family-community | 0.62 | 0.50 | 0.12 |
| Copy of Law and Public Service Lesson Plans | law-and-public-service | 0.62 | 0.50 | 0.12 |
| Law and Public Service Slides | law-and-public-service | 0.88 | 0.75 | 0.12 |
| Manufacturing Lesson | manufacturing | 0.88 | 0.75 | 0.12 |
| Manufacturing Lesson Plan | manufacturing | 0.50 | 0.62 | 0.12 |
| Professional Preparedness - Lesson Plan | professional-preparedness | 0.12 | 0.25 | 0.12 |
| Skills for Success-Career Ready Lesson Plan | professional-preparedness | 0.50 | 0.38 | 0.12 |
| Transportation Distribution and Logistics Lesson Plan | transportation-distribution | 0.62 | 0.50 | 0.12 |
| Architecture Construction Slides | architecture-construction | 0.75 | 0.75 | 0.00 |
| Career Clusters - Slides | career-cluster | 0.75 | 0.75 | 0.00 |
| Career Exploration Project Slides | career-exploration | 0.75 | 0.75 | 0.00 |
| What is Career Exploration Lesson Plan | career-exploration | 0.38 | 0.38 | 0.00 |
| Hospitality Tourism - Lesson Plan | hospitality-tourism | 0.50 | 0.50 | 0.00 |
| Law and Public Service Project Slides | law-and-public-service | 0.50 | 0.50 | 0.00 |
| Teaching and Training Education and Training Lesson Plan | teaching-and-training | 0.75 | 0.75 | 0.00 |
| Transportation Distribution and Logistics PowerPoint | transportation-distribution | 0.38 | 0.38 | 0.00 |

## Where the methods disagree (human-look queue)

- **Copy of Business Marketing Finance - Slides** (business-marketing) — spread 0.25: s1_completeness=0.75, s3_curriculum_own=0.50
- **Law and Public Service Lesson Plans** (law-and-public-service) — spread 0.25: s1_completeness=0.62, s3_curriculum_own=0.38
- **Skills for Success-Career Ready - Slides** (professional-preparedness) — spread 0.25: s1_completeness=0.62, s3_curriculum_own=0.38

## Agreement with hand-scored gold

| Method | Lessons compared | Mean abs error | Within tolerance |
|---|---|---|---|
| s1_completeness | 7 | 0.072 | 5 |
| s3_curriculum_own | 7 | 0.074 | 6 |

Lower mean-abs-error = closer to the human gold. This is the number that picks the winning method (see the lock-in step).
