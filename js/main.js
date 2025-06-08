document.addEventListener("DOMContentLoaded", () => {
  // Define edge color constants
  const DIM_PREREQ_COLOR = {
    color: "rgba(41, 128, 185, 0.15)",
    highlight: "rgba(52, 152, 219, 0.25)",
  }; // Dim blue
  const DIM_COREQ_COLOR = {
    color: "rgba(39, 174, 96, 0.15)",
    highlight: "rgba(46, 204, 113, 0.25)",
  }; // Dim green
  const HIGHLIGHT_PREREQ_COLOR = { color: "#2980b9", highlight: "#3498db" }; // Bright blue
  const HIGHLIGHT_COREQ_COLOR = { color: "#27ae60", highlight: "#2ecc71" }; // Bright green
  const graphContainer = document.getElementById("course-graph");
  const programSelect = document.getElementById("program-select");
  const courseSearchInput = document.getElementById("course-search");
  const searchButton = document.getElementById("search-button");
  const courseSidebar = document.getElementById("course-sidebar");
  const sidebarContent = document.getElementById("sidebar-content");
  const closeSidebarButton = document.getElementById("close-sidebar");
  const programSearchInput = document.getElementById("program-search-input");
  const programSuggestionsContainer = document.getElementById(
    "program-suggestions"
  );
  const categoryFilterSelect = document.getElementById(
    "category-filter-select"
  );
  const categorySearchInput = document.getElementById("category-search-input");
  const categorySuggestionsContainer = document.getElementById(
    "category-suggestions-container"
  );
  const loadingIndicator = document.getElementById("loading-indicator");

  // --- UI HELPER FUNCTIONS ---
  function showLoadingIndicator() {
    if (loadingIndicator) loadingIndicator.style.display = "block";
  }

  function hideLoadingIndicator() {
    if (loadingIndicator) loadingIndicator.style.display = "none";
  }

  let coursesData = [];
  let programsData = [];
  let network = null;
  let allNodesDataSet = new vis.DataSet(); // Use Vis DataSet for dynamic updates
  let allEdgesDataSet = new vis.DataSet(); // Use Vis DataSet for dynamic updates
  let allUniqueCategories = null;

  const COURSES_JSON_PATH = "data/mcgill_courses_processed.json";
  const PROGRAMS_JSON_PATH = "data/programs_and_courses.json";

  async function fetchData() {
    try {
      const [coursesResponse, programsResponse] = await Promise.all([
        fetch(COURSES_JSON_PATH),
        fetch(PROGRAMS_JSON_PATH),
      ]);

      if (!coursesResponse.ok)
        throw new Error(
          `Failed to load ${COURSES_JSON_PATH}: ${coursesResponse.statusText}`
        );
      if (!programsResponse.ok)
        throw new Error(
          `Failed to load ${PROGRAMS_JSON_PATH}: ${programsResponse.statusText}`
        );

      coursesData = await coursesResponse.json();
      console.log("Courses data loaded:", coursesData);

      // Populate allUniqueCategories as soon as coursesData is available
      if (coursesData && coursesData.length > 0) {
        const categoriesSet = new Set();
        coursesData.forEach((course) => {
          const group = extractGroup(course.code);
          if (group) categoriesSet.add(group); // Ensure group is not null/undefined
        });
        allUniqueCategories = Array.from(categoriesSet).sort();
        console.log("All unique categories populated:", allUniqueCategories);
      } else {
        allUniqueCategories = []; // Ensure it's an empty array if no courses or data
        console.log("No courses data to populate categories.");
      }

      // Log raw programs response before parsing
      const programsResponseClone = programsResponse.clone(); // Clone to read multiple times
      const rawProgramsText = await programsResponseClone.text();
      console.log("Raw programs_and_courses.json content:", rawProgramsText);

      programsData = await programsResponse.json();
      console.log(
        "Programs data loaded (parsed programs_and_courses.json):",
        programsData
      );

      console.log("Data fetched successfully:", {
        courses: coursesData.length,
        programs: programsData ? programsData.length : "undefined/null",
      });
    } catch (error) {
      console.error("Error fetching data:", error);
      graphContainer.innerHTML = `<p style="color: red; text-align: center; padding: 20px;">Error loading data: ${error.message}. Please ensure data files are in a 'data' subdirectory and accessible.</p>`;
    }
  }

  function displayProgramSuggestions(suggestions) {
    programSuggestionsContainer.innerHTML = ""; // Clear previous suggestions
    if (suggestions.length === 0) {
      programSuggestionsContainer.style.display = "none";
      return;
    }

    suggestions.forEach((suggestion) => {
      const div = document.createElement("div");
      div.textContent = suggestion.program;
      div.dataset.programName = suggestion.program; // Store program name for click handler
      // Click listener will be added via event delegation on the container
      programSuggestionsContainer.appendChild(div);
    });
    programSuggestionsContainer.style.display = "block";
  }

  function handleSuggestionClick(event) {
    if (event.target.tagName === "DIV" && event.target.dataset.programName) {
      const selectedProgram = event.target.dataset.programName;
      programSelect.value = selectedProgram;
      programSearchInput.value = selectedProgram; // Update input field as well
      programSuggestionsContainer.style.display = "none";
      // Trigger change event on the main program select to update graph
      const changeEvent = new Event("change");
      programSelect.dispatchEvent(changeEvent);
    }
  }

  function handleCategoryFilterChange() {
    const selectedCategory = categoryFilterSelect.value;
    const normalOpacity = 1.0;
    const dimOpacity = 0.2; // Dim enough to see, but clearly de-emphasized

    const allGraphNodes = allNodesDataSet.get({ returnType: "Array" });
    const nodesToUpdate = [];

    allGraphNodes.forEach((node) => {
      let newOpacity = normalOpacity;
      if (selectedCategory === "all") {
        newOpacity = normalOpacity;
      } else {
        // Check if the node's group matches the selected category.
        // The 'group' property is set in addRequirementGraphElements and generateGraphElements.
        if (node.group === selectedCategory) {
          newOpacity = normalOpacity;
        } else {
          newOpacity = dimOpacity;
        }
      }
      // Only update if opacity actually changes to avoid unnecessary updates
      if (node.opacity !== newOpacity) {
        nodesToUpdate.push({ id: node.id, opacity: newOpacity });
      }
    });

    if (nodesToUpdate.length > 0) {
      allNodesDataSet.update(nodesToUpdate);
    }
  }

  function handleCategorySuggestionClick(event) {
    if (event.target.tagName === "DIV" && event.target.dataset.categoryName) {
      const selectedCategory = event.target.dataset.categoryName;
      categoryFilterSelect.value = selectedCategory;
      categorySearchInput.value = event.target.textContent; // Use textContent for display
      categorySuggestionsContainer.style.display = "none";

      // Trigger change event on the main category select to apply filter
      const changeEvent = new Event("change");
      categoryFilterSelect.dispatchEvent(changeEvent);
    }
  }

  function handleCategorySearchInput() {
    const searchTerm = categorySearchInput.value;
    populateCategoryFilter(searchTerm);
  }

  function handleProgramSearchInput() {
    const query = programSearchInput.value.toLowerCase();
    if (query.length < 2) {
      // Only search if query is at least 2 chars
      programSuggestionsContainer.style.display = "none";
      return;
    }

    const filteredPrograms = programsData.filter(
      (program) =>
        program.program && program.program.toLowerCase().includes(query)
    );
    displayProgramSuggestions(filteredPrograms);
  }

  function populateCategoryFilter(searchTerm = "") {
    // Assumes allUniqueCategories is populated by the initial data load.
    if (!allUniqueCategories) {
      // This case should ideally not be hit if initialization order is correct.
      console.error(
        "allUniqueCategories is not populated when populateCategoryFilter is called."
      );
      if (categorySuggestionsContainer)
        categorySuggestionsContainer.style.display = "none";
      return;
    }

    if (allUniqueCategories.length === 0 && searchTerm === "") {
      // Only hide if truly empty and no search term
      // console.warn("No categories available to populate filter suggestions.");
      if (categorySuggestionsContainer)
        categorySuggestionsContainer.style.display = "none";
      // Don't return yet, still need to populate the hidden select if it's the first time.
    }

    // Populate the hidden select dropdown if it hasn't been done yet.
    // This is crucial for the category filter logic to work even if suggestions are not immediately visible.
    if (categoryFilterSelect && categoryFilterSelect.options.length <= 1) {
      categoryFilterSelect.innerHTML = "";
      const allOpt = document.createElement("option");
      allOpt.value = "all";
      allOpt.textContent = "--- All Categories ---";
      categoryFilterSelect.appendChild(allOpt);
      allUniqueCategories.forEach((cat) => {
        if (cat) {
          // Ensure category is not null or empty string
          const option = document.createElement("option");
          option.value = cat;
          option.textContent = cat;
          categoryFilterSelect.appendChild(option);
        }
      });
    }

    if (!categorySuggestionsContainer) return; // Guard against null container for suggestions
    categorySuggestionsContainer.innerHTML = ""; // Clear previous suggestions
    const searchTermLower = searchTerm.toLowerCase();

    const filteredCategories = allUniqueCategories.filter(
      (category) => category && category.toLowerCase().includes(searchTermLower) // Add null check for category
    );

    let suggestionsMade = false;

    // Add "All Categories" to suggestions if it matches search or if search is empty
    if (
      "--- all categories ---".includes(searchTermLower) ||
      searchTermLower === ""
    ) {
      const div = document.createElement("div");
      div.textContent = "--- All Categories ---";
      div.dataset.categoryName = "all";
      categorySuggestionsContainer.appendChild(div);
      suggestionsMade = true;
    }

    filteredCategories.forEach((category) => {
      if (category) {
        // Ensure category is not null or empty string
        const div = document.createElement("div");
        div.textContent = category;
        div.dataset.categoryName = category;
        categorySuggestionsContainer.appendChild(div);
        suggestionsMade = true;
      }
    });

    if (suggestionsMade) {
      categorySuggestionsContainer.style.display = "block";
    } else {
      categorySuggestionsContainer.style.display = "none";
    }
  }

  function populateProgramSelect() {
    console.log(
      "Entering populateProgramSelect. programsData:",
      programsData,
      "Length:",
      programsData ? programsData.length : "N/A"
    );
    // Add a default "Select a Program" option that is initially selected
    const defaultOption = document.createElement("option");
    defaultOption.value = ""; // Empty value, will not trigger a graph load
    defaultOption.textContent = "--- Select a Program ---";
    defaultOption.selected = true;
    defaultOption.disabled = true; // User cannot re-select it
    programSelect.appendChild(defaultOption);

    // Add "Show All Programs" option
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = "Show All Programs (Warning: Can be slow)";
    programSelect.appendChild(allOption);

    programsData.forEach((program, index) => {
      console.log(
        `Processing program at index ${index}:`,
        JSON.stringify(program, null, 2)
      ); // Log the program object for inspection
      if (
        program &&
        typeof program.program === "string" &&
        program.program.trim() !== ""
      ) {
        const option = document.createElement("option");
        option.value = program.program; // Use program.program
        option.textContent = program.program; // Use program.program
        programSelect.appendChild(option);
      } else {
        console.warn(
          `Skipping program at index ${index} due to missing or empty 'program' property. Program data:`,
          program
        );
      }
    });
  }

  function extractGroup(courseCode) {
    const prefix = courseCode.split("-")[0];
    const facultyMap = {
      ANAT: "Neuroscience",
      BIOL: "Neuroscience",
      CHEM: "Neuroscience",
      NEUR: "Neuroscience",
      NSCI: "Neuroscience",
      PHGY: "Neuroscience",
      PSYC: "Neuroscience",
      PSYT: "Neuroscience",
    };
    return facultyMap[prefix] || prefix;
  }

  // Get all relevant course codes for a given set of program courses (including all dependencies)
  function getRelevantCoursesForProgram(programCourseCodes) {
    const relevantCodes = new Set();
    // Start queue with only those program courses that actually exist in coursesData
    const queue = programCourseCodes.filter((code) =>
      coursesData.find((c) => c.code === code)
    );

    queue.forEach((code) => relevantCodes.add(code)); // Add initial valid courses to relevant set

    let head = 0; // Use a pointer for queue to avoid performance issues with Array.shift() on large arrays
    while (head < queue.length) {
      const currentCode = queue[head++];
      const course = coursesData.find((c) => c.code === currentCode);
      if (!course) continue;

      const addDependencies = (requirements) => {
        if (!requirements || !Array.isArray(requirements)) return;
        requirements.forEach((req) => {
          if (req.type === "COURSE") {
            if (
              coursesData.find((c) => c.code === req.code) &&
              !relevantCodes.has(req.code)
            ) {
              relevantCodes.add(req.code);
              queue.push(req.code);
            }
          } else if (req.type === "LOGICAL_OPERATOR" && req.conditions) {
            addDependencies(req.conditions);
          }
        });
      };

      addDependencies(course.prerequisites_parsed);
      addDependencies(course.corequisites_parsed);
    }
    return Array.from(relevantCodes);
  }

  // Generate node and edge objects for Vis.js based on a list of course codes
  function generateGraphElements(courseCodesToDisplay) {
    const idCounter = { logic: 0, textual: 0, nOfList: 0 }; // Counters for unique node IDs
    const nodesArray = [];
    const edgesArray = [];
    const displaySet = new Set(courseCodesToDisplay);

    displaySet.forEach((courseCode) => {
      const course = coursesData.find((c) => c.code === courseCode);
      if (!course) return;

      nodesArray.push({
        id: course.code,
        label: course.code,
        title: `${course.code}: ${course.title}`,
        group: extractGroup(course.code),
      });

      // Process its prerequisites using the new recursive function
      if (course.prerequisites_parsed) {
        course.prerequisites_parsed.forEach((reqDetail) => {
          addRequirementGraphElements(
            reqDetail,
            course.code,
            "prereq",
            displaySet,
            nodesArray,
            edgesArray,
            idCounter,
            course.code
          );
        });
      }
      // Process its corequisites using the new recursive function
      if (course.corequisites_parsed) {
        course.corequisites_parsed.forEach((reqDetail) => {
          addRequirementGraphElements(
            reqDetail,
            course.code,
            "coreq",
            displaySet,
            nodesArray,
            edgesArray,
            idCounter,
            course.code
          );
        });
      }
    });

    return { nodes: nodesArray, edges: edgesArray };
  }

  // Recursive function to add graph elements for requirements, including logic nodes
  function addRequirementGraphElements(
    requirement,
    targetNodeId,
    type,
    displaySet,
    nodesArray,
    edgesArray,
    idCounter,
    originalCourseCode
  ) {
    if (!requirement) return;

    if (requirement.type === "COURSE") {
      const courseCode = requirement.code;
      const courseData = coursesData.find((c) => c.code === courseCode);

      if (courseData) {
        // Check if the course exists in the main dataset
        // Add node for the prerequisite/corequisite course if not already added by main loop or other recursions
        if (!nodesArray.some((n) => n.id === courseCode)) {
          nodesArray.push({
            id: courseCode,
            label: courseCode,
            group: extractGroup(courseCode),
            title: courseData.title || courseCode,
            details: courseData,
          });
        }

        // Always add the edge from this course to the targetNodeId
        const edge = {
          from: courseCode,
          to: targetNodeId,
          arrows: "to",
          color: type === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR,
          dashes: type === "coreq",
          title: `${courseCode} ${
            type === "prereq"
              ? "is a prerequisite for"
              : "is a corequisite with"
          } ${
            targetNodeId.startsWith("logic_") ? "a condition group for" : ""
          } ${originalCourseCode}`,
          baseColorType: type,
          id: `${courseCode}_${targetNodeId}_${type}`,
        };
        if (!edgesArray.some((e) => e.id === edge.id)) {
          edgesArray.push(edge);
        }
      } else {
        console.warn(
          `Course ${courseCode} referenced as a requirement for ${originalCourseCode} but not found in coursesData.`
        );
      }
    } else if (requirement.type === "LOGICAL_OPERATOR") {
      idCounter.logic++;
      const operator = requirement.operator.toUpperCase(); // AND or OR
      const logicNodeGroup = operator === "AND" ? "AndNode" : "OrNode";
      const logicNodeId = `logic_${originalCourseCode}_${type}_${operator}_${idCounter.logic}`;

      // Add the logic node itself
      if (!nodesArray.some((n) => n.id === logicNodeId)) {
        nodesArray.push({
          id: logicNodeId,
          label: operator, // Vis.js will use group label if node label is same as group name
          group: logicNodeGroup,
          size: 12, // Slightly larger for visibility
          title: `${operator} condition for ${originalCourseCode}`,
        });
      }

      // Edge from the logic node to its target (either the main course or another logic node)
      const edgeToTarget = {
        from: logicNodeId,
        to: targetNodeId,
        arrows: "to",
        color: type === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR, // Style as per main type
        dashes: false, // Logic connections are not dashed for coreqs
        title: `This ${operator} group is a ${type} for ${
          targetNodeId.startsWith("logic_") ? "another condition group for" : ""
        } ${originalCourseCode}`,
        baseColorType: type, // Keep base type for coloring consistency
        id: `${logicNodeId}_${targetNodeId}_${type}`,
      };
      if (!edgesArray.some((e) => e.id === edgeToTarget.id)) {
        edgesArray.push(edgeToTarget);
      }

      // Recursively process conditions connecting to this new logic node
      if (requirement.conditions && requirement.conditions.length > 0) {
        requirement.conditions.forEach((condition) => {
          addRequirementGraphElements(
            condition,
            logicNodeId,
            type,
            displaySet,
            nodesArray,
            edgesArray,
            idCounter,
            originalCourseCode
          );
        });
      }
    } else if (requirement.type === "TEXTUAL") {
      idCounter.textual++;
      const textualNodeId = `textual_${originalCourseCode}_${type}_${idCounter.textual}`;
      const nodeLabel = requirement.text || "Textual requirement";

      if (!nodesArray.some((n) => n.id === textualNodeId)) {
        nodesArray.push({
          id: textualNodeId,
          label: nodeLabel,
          group: "TextualNode",
          title: `Textual: ${nodeLabel} (for ${originalCourseCode})`,
        });
      }

      const edgeToTarget = {
        from: textualNodeId,
        to: targetNodeId,
        arrows: "to",
        color: type === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR,
        dashes: false, // Textual requirements are not corequisites in terms of dashing
        title: `This textual condition is a ${type} for ${
          targetNodeId.startsWith("logic_") ? "a condition group for" : ""
        } ${originalCourseCode}`,
        baseColorType: type,
        id: `${textualNodeId}_${targetNodeId}_${type}`,
      };
      if (!edgesArray.some((e) => e.id === edgeToTarget.id)) {
        edgesArray.push(edgeToTarget);
      }
    } else if (requirement.type === "N_OF_LIST") {
      if (requirement.count === 1) {
        // Treat '1 of list' as a standard OR condition
        idCounter.logic++; // Use logic counter for OR node
        const orNodeId = `logic_${originalCourseCode}_${type}_OR_N_OF_1_${idCounter.logic}`;
        const orNodeGroup = "OrNode";

        if (!nodesArray.some((n) => n.id === orNodeId)) {
          nodesArray.push({
            id: orNodeId,
            label: "OR", // Vis.js will use group label if node label is same as group name
            group: orNodeGroup,
            size: 12,
            title: `OR condition (1 of list) for ${originalCourseCode}`,
            details: requirement, // Store original N_OF_LIST requirement for context
          });
        }

        // Edge from the new OR node to its target
        const edgeToTarget = {
          from: orNodeId,
          to: targetNodeId,
          arrows: "to",
          color: type === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR,
          dashes: false,
          title: `This OR group (1 of list) is a ${type} for ${
            targetNodeId.startsWith("logic_") ? "another condition for" : ""
          } ${originalCourseCode}`,
          baseColorType: type,
          id: `${orNodeId}_${targetNodeId}_${type}`,
        };
        if (!edgesArray.some((e) => e.id === edgeToTarget.id)) {
          edgesArray.push(edgeToTarget);
        }

        // Recursively process items in the list, connecting them to this new OR node
        if (requirement.conditions && requirement.conditions.length > 0) {
          requirement.conditions.forEach((itemInList) => {
            addRequirementGraphElements(
              itemInList,
              orNodeId,
              type,
              displaySet,
              nodesArray,
              edgesArray,
              idCounter,
              originalCourseCode
            );
          });
        }
      } else {
        // Handle 'N of list' where N > 1
        idCounter.nOfList++;
        const nOfListNodeId = `n_of_list_${originalCourseCode}_${type}_${requirement.count}_${idCounter.nOfList}`;
        const nodeLabel = `${requirement.count} of:`;

        if (!nodesArray.some((n) => n.id === nOfListNodeId)) {
          nodesArray.push({
            id: nOfListNodeId,
            label: nodeLabel,
            group: "NOfListNode",
            title: `${nodeLabel} (for ${originalCourseCode})`,
            details: requirement, // Store the requirement details
          });
        }

        // Edge from the N_OF_LIST node to its target
        const edgeToMainTarget = {
          from: nOfListNodeId,
          to: targetNodeId,
          arrows: "to",
          color: type === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR,
          dashes: false,
          title: `This '${nodeLabel}' group is a ${type} for ${
            targetNodeId.startsWith("logic_")
              ? "another condition group for"
              : ""
          } ${originalCourseCode}`,
          baseColorType: type,
          id: `${nOfListNodeId}_${targetNodeId}_${type}`,
        };
        if (!edgesArray.some((e) => e.id === edgeToMainTarget.id)) {
          edgesArray.push(edgeToMainTarget);
        }

        // Recursively process items in the list, connecting them to this N_OF_LIST node
        if (requirement.conditions && requirement.conditions.length > 0) {
          requirement.conditions.forEach((itemInList) => {
            addRequirementGraphElements(
              itemInList,
              nOfListNodeId,
              type,
              displaySet,
              nodesArray,
              edgesArray,
              idCounter,
              originalCourseCode
            );
          });
        }
      }
    }
  }

  // Update the Vis.js network with a specific set of courses
  function displayGraphForCourses(courseCodesToDisplay) {
    // Clear previous data from DataSets
    allNodesDataSet.clear();
    allEdgesDataSet.clear();

    if (!courseCodesToDisplay || courseCodesToDisplay.length === 0) {
      // If no courses to display, ensure the network is updated with empty DataSets
      if (network)
        network.setData({ nodes: allNodesDataSet, edges: allEdgesDataSet });
      return; // Exit if nothing to display
    }

    const { nodes, edges } = generateGraphElements(courseCodesToDisplay);

    // Deduplicate nodes by ID as a safeguard
    const uniqueNodesById = new Map();
    nodes.forEach((node) => {
      if (!uniqueNodesById.has(node.id)) {
        uniqueNodesById.set(node.id, node);
      } else {
        console.warn(
          `Duplicate node ID encountered and removed before rendering: ${node.id}.`
        );
      }
    });
    const finalNodes = Array.from(uniqueNodesById.values());

    // Deduplicate edges by ID as a safeguard
    const uniqueEdgesById = new Map();
    edges.forEach((edge) => {
      if (!uniqueEdgesById.has(edge.id)) {
        uniqueEdgesById.set(edge.id, edge);
      } else {
        console.warn(
          `Duplicate edge ID encountered and removed before rendering: ${edge.id}.`
        );
      }
    });
    const finalEdges = Array.from(uniqueEdgesById.values());

    console.log("Attempting to add unique nodes to Vis:", finalNodes.length);
    console.log("Attempting to add unique edges to Vis:", finalEdges.length);

    if (finalNodes.length > 0) {
      allNodesDataSet.add(finalNodes);
    }
    if (finalEdges.length > 0) {
      allEdgesDataSet.add(finalEdges);
    }

    // After adding data, ensure the network is updated and fits view
    if (network) {
      network.setData({ nodes: allNodesDataSet, edges: allEdgesDataSet });
      if (network.physics.options.enabled) {
        network.stabilize(); // Stabilize if physics is on
        network.once("stabilizationIterationsDone", function () {
          network.fit(); // Fit after stabilization
        });
      } else {
        network.fit(); // Fit directly if physics is off
      }
    }
  }

  // Initialize the Vis.js network object (the "shell") without any data initially
  function initializeNetworkShell() {
    const data = { nodes: allNodesDataSet, edges: allEdgesDataSet }; // Use the DataSets
    const options = {
      nodes: {
        shape: "box",
        margin: 10,
        font: { size: 12, face: "Arial" },
        borderWidth: 1,
        shadow: true,
      },
      edges: {
        width: 1,
        smooth: {
          type: "cubicBezier",
          forceDirection: "horizontal",
          roundness: 0.4,
        },
        shadow: true,
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: true,
        keyboard: true,
      },
      physics: {
        enabled: true,
        barnesHut: {
          gravitationalConstant: -3000, // Moderately reduced repulsion
          centralGravity: 0.2, // Increased attraction to the center
          springLength: 120, // Ideal length of an edge
          springConstant: 0.05, // Stiffness of the edges
          damping: 0.09, // Reduces oscillations
          avoidOverlap: 0.1, // Prevents nodes from overlapping too much
        },
        solver: "barnesHut", // Good for larger networks and clustering
        stabilization: {
          iterations: 1000,
          fit: true,
        },
      },
      groups: {
        Engineering: { color: { background: "#f0a30a", border: "#c88708" } },
        Science: { color: { background: "#74a8d0", border: "#5a86a9" } },
        Arts: { color: { background: "#98c591", border: "#7ca076" } },
        Management: { color: { background: "#f67280", border: "#c85c69" } },
        Medicine: { color: { background: "#c06c84", border: "#a0586e" } },
        AndNode: {
          shape: "diamond",
          size: 10,
          color: { background: "#bdc3c7", border: "#95a5a6" },
          font: { size: 10, color: "#34495e" },
          label: "AND",
        },
        OrNode: {
          shape: "ellipse",
          size: 10,
          color: { background: "#bdc3c7", border: "#95a5a6" },
          font: { size: 10, color: "#34495e" },
          label: "OR",
        },
        TextualNode: {
          shape: "box",
          color: { background: "#e0e0e0", border: "#cccccc" },
          font: { multi: true, size: 10, color: "#555555", align: "left" },
          margin: 8,
          widthConstraint: { maximum: 150 },
        },
        NOfListNode: {
          shape: "hexagon",
          size: 12,
          color: { background: "#a2ded0", border: "#87bcaf" },
          font: { size: 10, color: "#34495e" },
        },
      },
    };

    network = new vis.Network(graphContainer, data, options);
    setupEventListeners();
  }

  function setupEventListeners() {
    network.on("click", handleNetworkClick);

    network.on("dragStart", function (params) {
      if (params.nodes && params.nodes.length > 0) {
        const updates = params.nodes.map((nodeId) => ({
          id: nodeId,
          fixed: false, // Unfix node when dragging starts
        }));
        allNodesDataSet.update(updates);
      }
    });

    network.on("dragEnd", function (params) {
      if (params.nodes && params.nodes.length > 0) {
        const updates = params.nodes.map((nodeId) => ({
          id: nodeId,
          fixed: true, // Fixes node at its current position after drag
        }));
        allNodesDataSet.update(updates);
      }
    });
    programSelect.addEventListener("change", handleProgramChange);
    searchButton.addEventListener("click", handleSearch);
    courseSearchInput.addEventListener("keypress", (event) => {
      if (event.key === "Enter") handleSearch();
    });
    closeSidebarButton.addEventListener("click", hideSidebar);

    // Program Search Event Listeners
    if (programSearchInput) {
      programSearchInput.addEventListener("input", handleProgramSearchInput);
    }

    if (programSuggestionsContainer) {
      programSuggestionsContainer.addEventListener(
        "click",
        handleSuggestionClick
      );
    }

    if (categoryFilterSelect) {
      categoryFilterSelect.addEventListener(
        "change",
        handleCategoryFilterChange
      );
    }

    if (categorySearchInput) {
      categorySearchInput.addEventListener("input", handleCategorySearchInput);
      // Show suggestions on focus as well, if desired
      categorySearchInput.addEventListener("focus", () =>
        populateCategoryFilter(categorySearchInput.value)
      );
    }

    if (categorySuggestionsContainer) {
      categorySuggestionsContainer.addEventListener(
        "click",
        handleCategorySuggestionClick
      );
    }

    // Global click listener to hide program suggestions when clicking outside
    document.addEventListener("click", function (event) {
      // Hide program suggestions
      if (programSearchInput && programSuggestionsContainer) {
        if (
          !programSearchInput.contains(event.target) &&
          !programSuggestionsContainer.contains(event.target)
        ) {
          programSuggestionsContainer.style.display = "none";
        }
      }
      // Hide category suggestions
      if (categorySearchInput && categorySuggestionsContainer) {
        if (
          !categorySearchInput.contains(event.target) &&
          !categorySuggestionsContainer.contains(event.target)
        ) {
          categorySuggestionsContainer.style.display = "none";
        }
      }
    });
  }

  function handleNetworkClick(params) {
    const clickedNodeId = params.nodes.length > 0 ? params.nodes[0] : null;

    if (clickedNodeId) {
      const course = coursesData.find((c) => c.code === clickedNodeId);
      if (course) updateSidebar(course);
    }
    // No 'else hideSidebar()' here, sidebar visibility is managed by its own button and program changes.

    // Update edge colors based on click
    const edgesToUpdate = allEdgesDataSet
      .get({ returnType: "Array" })
      .map((edge) => {
        let newColorObj;
        // Fallback for baseColorType if somehow missing (e.g. from very old data not cleared)
        const baseType =
          edge.baseColorType || (edge.dashes ? "coreq" : "prereq");

        if (
          clickedNodeId &&
          (edge.from === clickedNodeId || edge.to === clickedNodeId)
        ) {
          newColorObj =
            baseType === "prereq"
              ? HIGHLIGHT_PREREQ_COLOR
              : HIGHLIGHT_COREQ_COLOR;
        } else {
          newColorObj =
            baseType === "prereq" ? DIM_PREREQ_COLOR : DIM_COREQ_COLOR;
        } // Closes the else for color assignment
        return { id: edge.id, color: newColorObj }; // Return object with id and new color
      }); // Closes the .map()

    if (edgesToUpdate.length > 0) {
      allEdgesDataSet.update(edgesToUpdate);
    }

    // Update node opacities
    const allNodes = allNodesDataSet.get({ returnType: "Array" });
    let nodesToUpdate = [];

    if (clickedNodeId) {
      const connectedNodes = new Set();
      connectedNodes.add(clickedNodeId);
      // Ensure 'network' is defined and accessible here. It should be, as it's a global.
      if (network && typeof network.getConnectedNodes === "function") {
        network
          .getConnectedNodes(clickedNodeId)
          .forEach((nodeId) => connectedNodes.add(nodeId));
      }

      allNodes.forEach((node) => {
        const isConnected = connectedNodes.has(node.id);
        let newOpacity = isConnected ? 1 : 0.2;
        nodesToUpdate.push({ id: node.id, opacity: newOpacity });
      });
    } else {
      // No node clicked, reset all opacities
      allNodes.forEach((node) => {
        nodesToUpdate.push({ id: node.id, opacity: 1 });
      });
    }

    if (nodesToUpdate.length > 0) {
      allNodesDataSet.update(nodesToUpdate);
    }
  } // End of handleNetworkClick

  // Restore the updateSidebar function definition
  function updateSidebar(course) {
    let prereqsHTML = course.prerequisites_raw
      ? `<div class="raw-reqs">${course.prerequisites_raw}</div>`
      : "None";
    let coreqsHTML = course.corequisites_raw
      ? `<div class="raw-reqs">${course.corequisites_raw}</div>`
      : "None";

    sidebarContent.innerHTML = `
            <h2>${course.code} - ${course.title}</h2>
            <p><strong>Credits:</strong> ${course.credits || "N/A"}</p>
            <h3>Description</h3>
            <p>${course.description || "No description available."}</p>
            <h3>Prerequisites (Raw)</h3>
            ${prereqsHTML}
            <h3>Corequisites (Raw)</h3>
            ${coreqsHTML}`;
    courseSidebar.classList.add("visible");
    courseSidebar.classList.remove("hidden");
  }

  function hideSidebar() {
    courseSidebar.classList.remove("visible");
    courseSidebar.classList.add("hidden");
  }

  // Update the Vis.js network with a specific set of courses
  function displayGraphForCourses(courseCodesToDisplay) {
    // Clear previous data from DataSets
    allNodesDataSet.clear();
    allEdgesDataSet.clear();

    if (!courseCodesToDisplay || courseCodesToDisplay.length === 0) {
      // If no courses to display, ensure the network is updated with empty DataSets
      if (network)
        network.setData({ nodes: allNodesDataSet, edges: allEdgesDataSet });
      return; // Exit if nothing to display
    }

    const { nodes, edges } = generateGraphElements(courseCodesToDisplay);

    // Deduplicate nodes by ID
    const uniqueNodesById = new Map();
    nodes.forEach((node) => {
      if (!uniqueNodesById.has(node.id)) {
        uniqueNodesById.set(node.id, node);
      }
    });

    allNodesDataSet.add(Array.from(uniqueNodesById.values()));
    allEdgesDataSet.add(edges);

    if (network) {
      network.setData({ nodes: allNodesDataSet, edges: allEdgesDataSet });
    }
  }

  function handleProgramChange() {
    showLoadingIndicator();
    const selectedProgramName = programSelect.value;
    hideSidebar();

    if (selectedProgramName === "") {
      // Handle the "--- Select a Program ---" option
      displayGraphForCourses([]); // Clear the graph
      hideLoadingIndicator();
    } else if (selectedProgramName === "all") {
      // Handle "Show All Programs"
      const allCourseCodes = coursesData.map((c) => c.code);
      displayGraphForCourses(allCourseCodes);
      hideLoadingIndicator();
    } else {
      // Handle a specific program selection
      const program = programsData.find(
        (p) => p.program === selectedProgramName
      );
      if (program && program.courses) {
        displayGraphForCourses(program.courses); // Load only courses for this program
      } else {
        // Program not found or has no courses array
        console.warn(
          `Program "${selectedProgramName}" not found or has no courses defined.`
        );
        displayGraphForCourses([]); // Clear graph
      }
      hideLoadingIndicator(); // Always hide after attempting to load a specific program
    }
  }

  function handleSearch() {
    const searchTerm = courseSearchInput.value.trim().toUpperCase();
    if (!searchTerm) return;

    if (allNodesDataSet.get(searchTerm)) {
      // Search in current DataSet
      network.focus(searchTerm, {
        scale: 1.5,
        animation: { duration: 1000, easingFunction: "easeInOutQuad" },
      });
      network.selectNodes([searchTerm]);

      const course = coursesData.find((c) => c.code === searchTerm);
      if (course) updateSidebar(course);
    } else {
      alert(
        `Course code "${searchTerm}" not found in the current view. Try selecting "Show All Programs" or a different program.`
      );
    }
  }

  async function initApp() {
    await fetchData();
    if (coursesData.length > 0 && programsData.length > 0) {
      populateProgramSelect();
      populateCategoryFilter();
      initializeNetworkShell(); // Initialize network shell, data loaded on program change
    } else {
      console.log("Initialization aborted due to data loading issues.");
    }
  }

  initApp();
});
