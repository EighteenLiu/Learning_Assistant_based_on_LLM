<template>
  <li class="mind-map-node">
    <div class="mind-map-node__label">{{ node.title }}</div>
    <ul v-if="node.children?.length" class="mind-map-node__children">
      <MindMapNode v-for="(child, index) in node.children" :key="`${child.title}-${index}`" :node="child" />
    </ul>
  </li>
</template>

<script setup lang="ts">
export interface MindMapNodeData {
  title: string;
  children?: MindMapNodeData[];
}

defineProps<{
  node: MindMapNodeData;
}>();
</script>

<style scoped>
.mind-map-node {
  position: relative;
  list-style: none;
  text-align: center;
  padding: 0 8px;
}

.mind-map-node__label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 140px;
  max-width: 240px;
  min-height: 46px;
  padding: 10px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.96));
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
  line-height: 1.6;
}

.mind-map-node__children {
  position: relative;
  display: flex;
  justify-content: center;
  gap: 22px;
  margin: 20px 0 0;
  padding: 28px 10px 0;
}

.mind-map-node__children::before {
  content: "";
  position: absolute;
  top: 0;
  left: calc(50% - 1px);
  width: 2px;
  height: 16px;
  background: rgba(148, 163, 184, 0.9);
}

.mind-map-node__children > .mind-map-node::before {
  content: "";
  position: absolute;
  top: -12px;
  left: calc(50% - 1px);
  width: 2px;
  height: 12px;
  background: rgba(148, 163, 184, 0.9);
}

.mind-map-node__children > .mind-map-node::after {
  content: "";
  position: absolute;
  top: -12px;
  left: -11px;
  width: calc(100% + 22px);
  height: 2px;
  background: rgba(148, 163, 184, 0.9);
}

.mind-map-node__children > .mind-map-node:first-child::after {
  left: 50%;
  width: calc(50% + 11px);
}

.mind-map-node__children > .mind-map-node:last-child::after {
  width: calc(50% + 11px);
}

.mind-map-node__children > .mind-map-node:only-child::after {
  display: none;
}

@media (max-width: 960px) {
  .mind-map-node__children {
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding-top: 18px;
  }

  .mind-map-node__children > .mind-map-node::before {
    top: -16px;
    height: 16px;
  }

  .mind-map-node__children > .mind-map-node::after {
    display: none;
  }
}
</style>
