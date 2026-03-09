Design a personal dashboard/homepage interface based on the following specifications. The interface should support both Chinese and English languages (show when choose the language in header menu bar).

**Global Elements:**

- **Header Menu Bar:** Refer to the provided reference file for the design style. (TopMenu.tsx).
- **Style Template: background4.html**
- Product Name: Careering.

**1. Left Sidebar**
The sidebar should contain the following elements, arranged vertically:

- User Avatar
- User Nickname
- **Current Progress** (Navigation Item)
- **Report** (Navigation Item)
- **Usage Guide** (Navigation Item)
- **Help Center** (Navigation Item)
- **Recycle Bin** (Navigation Item)
- **Setting** (Navigation Item)

**2. Main Content Area**
The main area displays the content of the selected sidebar item. The default view is the "Current Progress" page.

**2.1. Current Progress Page (Default Sub-page)**

- **Function:** Displays a list of progress items.
- **List Item:** Each item in the list represents a user journey and contains a **Path Diagram**.
- **Path Diagram Details:**
    - The diagram consists of **five nodes** in sequence: **Value**, **Strengths**, **Passion**, **Purpose**, and **Exploration**.
    - **Interaction:** Clicking any node should resume the conversation, navigating the user to the corresponding chat page for that topic.
    - **Visual State for Incomplete Nodes:** Nodes that the user has not yet completed should be visually distinct (e.g., greyed out/desaturated).
    - **Hover State for Incomplete Nodes:** When the user hovers over an incomplete/greyed-out node, a "forbidden" or "not allowed" cursor/symbol (e.g., a 🚫 icon) should appear.

**2.2. Report Page**

- **Layout:** Display reports in a list format. One item in list contains master report and its sub-reports.
- **Report Structure (Hierarchical):**
    - **Master Report:** The final comprehensive career development plan report.
    - **Sub-reports:** Displayed in four sections/columns, corresponding to the four different topics:
        1. Values
        2. Strengths
        3. Passion
        4. Purpose
- **Item Actions:** Each report item (both master and sub-reports) must have icons/buttons for the following actions:
    - Download
    - Share
    - Delete

**3. Navigation & Interaction Logic**

- **Default View:** Navigating to the personal homepage from any other page should default to displaying the "Current Progress" sub-page.