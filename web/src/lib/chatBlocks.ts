import type {Message} from '../types';

export type ChatBlock =
  | {type: 'dialogue'; messages: Message[]}
  | {type: 'forge'; activities: Message[]; products: Message[]};

export function groupChatBlocks(messages: Message[]): ChatBlock[] {
  const blocks: ChatBlock[] = [];
  for (const message of messages) {
    const last = blocks[blocks.length - 1];
    if (message.role === 'activity' || message.role === 'product') {
      if (last?.type === 'forge') {
        if (message.role === 'activity') last.activities.push(message);
        else last.products.push(message);
      } else {
        blocks.push({type: 'forge', activities: message.role === 'activity' ? [message] : [], products: message.role === 'product' ? [message] : []});
      }
    } else {
      if (last?.type === 'dialogue') {
        last.messages.push(message);
      } else {
        blocks.push({type: 'dialogue', messages: [message]});
      }
    }
  }
  return blocks;
}

export function hasRunningActivity(block: ChatBlock): boolean {
  if (block.type !== 'forge') return false;
  return block.activities.some((a) => a.status === 'running');
}
